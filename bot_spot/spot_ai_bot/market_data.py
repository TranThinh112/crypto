from statistics import mean

from spot_ai_bot.config import Settings
from spot_ai_bot.exchange import ExchangeClient
from spot_ai_bot.models import AssetGroup, MarketCandidate
from spot_ai_bot.okx_market import scan_okx_public, scan_okx_spot_universe


async def scan_market(settings: Settings | None = None) -> list[MarketCandidate]:
    if settings:
        try:
            candidates = await _scan_crypto_market(settings)
            if candidates:
                return candidates
            return await _scan_exchange_fallback(settings, "Exchange returned no candidates.")
        except Exception as exc:
            return await _scan_exchange_fallback(settings, f"{type(exc).__name__}: {exc}")
    return _fixture_candidates()


async def _scan_exchange_fallback(settings: Settings, reason: str) -> list[MarketCandidate]:
    symbols = [symbol.strip() for symbol in settings.market_symbols.split(",") if symbol.strip()]
    if settings.exchange_name.lower() == "okx":
        try:
            candidates = await _scan_okx_market(settings, symbols)
            if candidates:
                return candidates
        except Exception as exc:
            reason = f"{reason}; OKX REST fallback failed: {type(exc).__name__}: {exc}"
    return _fixture_candidates(reason)


async def _scan_crypto_market(settings: Settings) -> list[MarketCandidate]:
    if settings.exchange_name.lower() == "okx":
        symbols = [symbol.strip() for symbol in settings.market_symbols.split(",") if symbol.strip()]
        return await _scan_okx_market(settings, symbols)

    symbols = [symbol.strip() for symbol in settings.market_symbols.split(",") if symbol.strip()]
    client = ExchangeClient(settings)
    try:
        candidates: list[MarketCandidate] = []
        for symbol in symbols:
            ticker = await client.ticker(symbol)
            candles = await client.ohlcv(symbol)
            closes = [float(candle[4]) for candle in candles if candle[4]]
            if not closes or ticker.last <= 0:
                continue

            short_ma = mean(closes[-12:])
            long_ma = mean(closes[-48:]) if len(closes) >= 48 else mean(closes)
            returns = [
                abs((closes[i] - closes[i - 1]) / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1]
            ]
            trend_score = _score_ratio(short_ma / long_ma if long_ma else 1, low=0.98, high=1.04)
            liquidity_score = _score_ratio(ticker.quote_volume, low=1_000_000, high=100_000_000)
            volatility_score = min(1.0, (mean(returns) if returns else 0) / 0.025)
            candidates.append(
                MarketCandidate(
                    group=AssetGroup.crypto,
                    symbol=symbol.replace("/", ""),
                    price=ticker.last,
                    trend_score=round(trend_score, 4),
                    liquidity_score=round(liquidity_score, 4),
                    volatility_score=round(volatility_score, 4),
                    metadata={
                        "data_source": "live",
                        "exchange": settings.exchange_name,
                        "exchange_symbol": symbol,
                        "quote_volume": ticker.quote_volume,
                        "change_pct": ticker.percentage,
                    },
                )
            )
        return candidates
    finally:
        await client.close()


def _score_ratio(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def _fixture_candidates(reason: str = "No settings supplied.") -> list[MarketCandidate]:
    metadata = {"data_source": "fallback", "fallback_reason": reason}
    return [
        MarketCandidate(group=AssetGroup.crypto, symbol="BTCUSDT", price=118000, trend_score=0.72, liquidity_score=0.96, volatility_score=0.42, metadata=metadata),
        MarketCandidate(group=AssetGroup.crypto, symbol="ETHUSDT", price=3800, trend_score=0.68, liquidity_score=0.92, volatility_score=0.48, metadata=metadata),
        MarketCandidate(group=AssetGroup.stocks, symbol="SPY", price=620, trend_score=0.58, liquidity_score=0.95, volatility_score=0.25, metadata=metadata),
        MarketCandidate(group=AssetGroup.commodities, symbol="GLD", price=230, trend_score=0.62, liquidity_score=0.88, volatility_score=0.30, metadata=metadata),
    ]

async def _scan_okx_market(settings: Settings, symbols: list[str]) -> list[MarketCandidate]:
    if settings.market_scan_expand_universe_enabled:
        return await scan_okx_spot_universe(
            symbols,
            max_symbols=settings.market_scan_universe_max_symbols,
            anti_pump_max_24h_change_pct=settings.anti_pump_max_24h_change_pct,
            anti_pump_near_resistance_pct=settings.anti_pump_near_resistance_pct,
        )
    return await scan_okx_public(symbols)
