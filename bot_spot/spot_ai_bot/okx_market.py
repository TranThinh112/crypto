from statistics import mean

import httpx

from spot_ai_bot.candles import detect_patterns
from spot_ai_bot.db import active_shortlist_symbols
from spot_ai_bot.models import AssetGroup, MarketCandidate


def to_okx_inst_id(symbol: str) -> str:
    return symbol.strip().replace("/", "-").upper()

async def okx_last_price(inst_id: str) -> float | None:
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=15) as client:
        response = await client.get("/api/v5/market/ticker", params={"instId": to_okx_inst_id(inst_id)})
        response.raise_for_status()
        data = response.json().get("data") or []
        if not data:
            return None
        try:
            return float(data[0].get("last") or 0)
        except (TypeError, ValueError):
            return None

async def okx_spot_last_prices() -> dict[str, float]:
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=15) as client:
        response = await client.get("/api/v5/market/tickers", params={"instType": "SPOT"})
        response.raise_for_status()
        prices = {}
        for item in response.json().get("data") or []:
            inst_id = str(item.get("instId") or "").upper()
            try:
                prices[inst_id] = float(item.get("last") or 0)
            except (TypeError, ValueError):
                continue
        return prices

async def okx_spot_active_inst_ids() -> list[str]:
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=15) as client:
        response = await client.get("/api/v5/public/instruments", params={"instType": "SPOT"})
        response.raise_for_status()
        inst_ids: list[str] = []
        for item in response.json().get("data") or []:
            inst_id = str(item.get("instId") or "").upper()
            quote_ccy = str(item.get("quoteCcy") or "").upper()
            state = str(item.get("state") or "").lower()
            if inst_id.endswith("-USDT") and quote_ccy == "USDT" and state == "live":
                inst_ids.append(inst_id)
        return inst_ids

async def scan_okx_spot_universe(
    priority_symbols: list[str],
    max_symbols: int = 200,
    anti_pump_max_24h_change_pct: float = 6.0,
    anti_pump_near_resistance_pct: float = -1.5,
) -> list[MarketCandidate]:
    priority = [to_okx_inst_id(symbol) for symbol in priority_symbols if symbol.strip()]
    shortlist_symbols = set(await active_shortlist_symbols())
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=20) as client:
        tickers_response = await client.get("/api/v5/market/tickers", params={"instType": "SPOT"})
        tickers_response.raise_for_status()
        ticker_map: dict[str, dict] = {}
        for item in tickers_response.json().get("data") or []:
            inst_id = str(item.get("instId") or "").upper()
            ticker_map[inst_id] = item

        active_inst_ids = await okx_spot_active_inst_ids()
        ranked_inst_ids = []
        for inst_id in priority:
            if inst_id in ticker_map:
                ranked_inst_ids.append(inst_id)
        extras = [
            inst_id
            for inst_id in active_inst_ids
            if inst_id not in ranked_inst_ids and inst_id in ticker_map
        ]
        extras.sort(key=lambda inst_id: _to_float(ticker_map.get(inst_id, {}).get("volCcy24h")), reverse=True)
        ranked_inst_ids.extend(extras[: max(0, max_symbols - len(ranked_inst_ids))])
        for inst_id in sorted(shortlist_symbols):
            if inst_id in ticker_map and inst_id not in ranked_inst_ids:
                ranked_inst_ids.append(inst_id)

        full_priority_set = set(priority) | shortlist_symbols
        candidates: list[MarketCandidate] = []
        for inst_id in ranked_inst_ids:
            ticker = ticker_map.get(inst_id) or {}
            price = _to_float(ticker.get("last"))
            quote_volume = _to_float(ticker.get("volCcy24h"))
            open_24h = _to_float(ticker.get("open24h") or price or 0)
            change_pct = ((price - open_24h) / open_24h * 100) if open_24h else 0
            liquidity_score = _score_ratio(quote_volume, low=1_000_000, high=100_000_000)
            trend_score = _score_ratio(max(-10.0, min(10.0, change_pct)), low=-2.0, high=2.0)
            volatility_score = min(1.0, abs(change_pct) / 10.0)
            shortlist_candidate, shortlist_score, shortlist_reason = _should_shortlist(
                trend_score,
                liquidity_score,
                volatility_score,
                change_pct,
            )
            metadata = {
                "data_source": "live",
                "exchange": "okx",
                "exchange_symbol": inst_id.replace("-", "/"),
                "crypto_sector": _classify_crypto_sector(inst_id),
                "quote_volume": quote_volume,
                "change_pct": round(change_pct, 4),
                "scan_mode": "full" if inst_id in full_priority_set else "light",
                "shortlist_candidate": shortlist_candidate,
                "shortlist_score": round(shortlist_score, 4),
                "shortlist_reason": shortlist_reason,
                "anti_pump_max_24h_change_pct": anti_pump_max_24h_change_pct,
                "anti_pump_near_resistance_pct": anti_pump_near_resistance_pct,
            }
            if inst_id in full_priority_set:
                candle_response = await client.get(
                    "/api/v5/market/candles",
                    params={"instId": inst_id, "bar": "4H", "limit": "48"},
                )
                candle_response.raise_for_status()
                candles = candle_response.json().get("data") or []
                closes = [float(candle[4]) for candle in reversed(candles) if candle[4]]
                highs = [float(candle[2]) for candle in reversed(candles) if candle[2]]
                lows = [float(candle[3]) for candle in reversed(candles) if candle[3]]
                if closes:
                    short_ma = mean(closes[-12:])
                    long_ma = mean(closes[-48:]) if len(closes) >= 48 else mean(closes)
                    returns = [
                        abs((closes[i] - closes[i - 1]) / closes[i - 1])
                        for i in range(1, len(closes))
                        if closes[i - 1]
                    ]
                    trend_score = _score_ratio(short_ma / long_ma if long_ma else 1, low=0.98, high=1.04)
                    volatility_score = min(1.0, (mean(returns) if returns else 0) / 0.025)
                    resistance = max(highs[-72:]) if highs else price
                    support = min(lows[-72:]) if lows else price
                    drawdown = ((price - resistance) / resistance * 100) if resistance else 0
                    pattern_hits = detect_patterns(list(reversed(candles)), support=support, resistance=resistance)
                    pattern_info = pattern_hits[0] if pattern_hits else None
                    metadata.update(
                        {
                            "support_usdt": round(support, 8),
                            "resistance_usdt": round(resistance, 8),
                            "drawdown_from_resistance_pct": round(drawdown, 4),
                            "candlestick_patterns": pattern_hits[:5],
                            "candlestick_pattern": pattern_info["pattern"] if pattern_info else None,
                            "candlestick_bias": pattern_info["bias"] if pattern_info else None,
                            "candlestick_confidence": pattern_info["confidence"] if pattern_info else None,
                        }
                    )
                    if inst_id not in priority:
                        shortlist_candidate, shortlist_score, shortlist_reason = _should_shortlist(
                            trend_score,
                            liquidity_score,
                            volatility_score,
                            change_pct,
                        )
                        metadata["shortlist_candidate"] = shortlist_candidate
                        metadata["shortlist_score"] = round(shortlist_score, 4)
                        metadata["shortlist_reason"] = shortlist_reason
            candidates.append(
                MarketCandidate(
                    group=AssetGroup.crypto,
                    symbol=inst_id.replace("-", ""),
                    price=price,
                    trend_score=round(trend_score, 4),
                    liquidity_score=round(liquidity_score, 4),
                    volatility_score=round(volatility_score, 4),
                    metadata=metadata,
                )
            )
        return candidates


async def scan_okx_public(symbols: list[str]) -> list[MarketCandidate]:
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=15) as client:
        candidates: list[MarketCandidate] = []
        for symbol in symbols:
            inst_id = to_okx_inst_id(symbol)
            ticker_response = await client.get("/api/v5/market/ticker", params={"instId": inst_id})
            ticker_response.raise_for_status()
            ticker_payload = ticker_response.json()
            ticker_data = ticker_payload.get("data") or []
            if not ticker_data:
                continue
            ticker = ticker_data[0]

            candle_response = await client.get(
                "/api/v5/market/candles",
                params={"instId": inst_id, "bar": "4H", "limit": "48"},
            )
            candle_response.raise_for_status()
            candle_payload = candle_response.json()
            candles = candle_payload.get("data") or []
            closes = [float(candle[4]) for candle in reversed(candles) if candle[4]]
            highs = [float(candle[2]) for candle in reversed(candles) if candle[2]]
            lows = [float(candle[3]) for candle in reversed(candles) if candle[3]]
            if not closes:
                continue

            price = float(ticker.get("last") or 0)
            quote_volume = float(ticker.get("volCcy24h") or 0)
            open_24h = float(ticker.get("open24h") or price or 0)
            change_pct = ((price - open_24h) / open_24h * 100) if open_24h else 0
            short_ma = mean(closes[-12:])
            long_ma = mean(closes[-48:]) if len(closes) >= 48 else mean(closes)
            returns = [
                abs((closes[i] - closes[i - 1]) / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1]
            ]
            trend_score = _score_ratio(short_ma / long_ma if long_ma else 1, low=0.98, high=1.04)
            liquidity_score = _score_ratio(quote_volume, low=1_000_000, high=100_000_000)
            volatility_score = min(1.0, (mean(returns) if returns else 0) / 0.025)
            resistance = max(highs[-72:]) if highs else price
            support = min(lows[-72:]) if lows else price
            drawdown = ((price - resistance) / resistance * 100) if resistance else 0
            pattern_hits = detect_patterns(list(reversed(candles)), support=support, resistance=resistance)
            pattern_info = pattern_hits[0] if pattern_hits else None

            candidates.append(
                MarketCandidate(
                    group=AssetGroup.crypto,
                    symbol=inst_id.replace("-", ""),
                    price=price,
                    trend_score=round(trend_score, 4),
                    liquidity_score=round(liquidity_score, 4),
                    volatility_score=round(volatility_score, 4),
                    metadata={
                        "data_source": "live",
                        "exchange": "okx",
                        "exchange_symbol": inst_id,
                        "crypto_sector": _classify_crypto_sector(inst_id),
                        "quote_volume": quote_volume,
                        "change_pct": round(change_pct, 4),
                        "support_usdt": round(support, 8),
                        "resistance_usdt": round(resistance, 8),
                        "drawdown_from_resistance_pct": round(drawdown, 4),
                        "candlestick_patterns": pattern_hits[:5],
                        "candlestick_pattern": pattern_info["pattern"] if pattern_info else None,
                        "candlestick_bias": pattern_info["bias"] if pattern_info else None,
                        "candlestick_confidence": pattern_info["confidence"] if pattern_info else None,
                    },
                )
            )
        return candidates


def _score_ratio(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)

def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _classify_crypto_sector(inst_id: str) -> str:
    symbol = inst_id.replace("-", "").upper()
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    layer1 = {
        "BTC", "ETH", "SOL", "BNB", "ADA", "AVAX", "DOT", "ATOM", "NEAR",
        "SUI", "APT", "TON", "TRX", "XRP", "LTC", "BCH", "SEI", "INJ",
    }
    layer2 = {"ARB", "OP", "STRK", "IMX", "MATIC", "POL", "ZK", "STX", "TAO"}
    ai = {"FET", "RENDER", "RNDR", "WLD", "ARKM", "AIOZ", "IO", "AGIX", "OCEAN", "NMR"}
    defi = {"UNI", "AAVE", "CRV", "COMP", "MKR", "LDO", "SNX", "DYDX", "PENDLE", "GMX"}
    meme = {"DOGE", "SHIB", "PEPE", "BONK", "FLOKI", "WIF", "BRETT", "PENGU"}
    infra = {"LINK", "FIL", "AR", "TIA", "HNT", "GRT", "DOT", "RNDR"}
    stable = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE"}
    if base in stable:
        return "stable"
    if base in layer1:
        return "layer1"
    if base in layer2:
        return "layer2"
    if base in ai:
        return "ai"
    if base in defi:
        return "defi"
    if base in meme:
        return "meme"
    if base in infra:
        return "infra"
    return "other"

def _should_shortlist(trend_score: float, liquidity_score: float, volatility_score: float, change_pct: float) -> tuple[bool, float, str]:
    score = (trend_score * 0.45) + (liquidity_score * 0.35) + ((1.0 - min(1.0, volatility_score)) * 0.15) + (min(1.0, abs(change_pct) / 8.0) * 0.05)
    if trend_score >= 0.62 and liquidity_score >= 0.55 and volatility_score <= 0.90:
        return True, score, "mat_tinh_hinh_thi_truong_dang_chu_y"
    if abs(change_pct) >= 4.0 and liquidity_score >= 0.50:
        return True, score, "bien_dong_manh_can_theo_doi"
    return False, score, "chua_du_muc_do_quan_tam"
