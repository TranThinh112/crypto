from spot_ai_bot.ai import AIAdvisor
from spot_ai_bot.config import Settings
from spot_ai_bot.db import all_docs
from spot_ai_bot.models import PositionManagementProposal
from spot_ai_bot.okx_market import scan_okx_public
from spot_ai_bot.portfolio import spot_portfolio

STABLE_ASSETS = {"USDT", "USDC", "USD"}


async def evaluate_positions(settings: Settings, force_ai: bool = False) -> dict:
    portfolio = await spot_portfolio(settings)
    buy_history = await all_docs("buy_history", limit=1000)
    held_assets = [
        item for item in portfolio.get("assets", [])
        if item.get("asset") not in STABLE_ASSETS
    ]
    candidates = await _candidate_map(settings, held_assets)
    advisor = AIAdvisor(settings)
    proposals = []
    ai_calls = 0

    for asset in held_assets:
        symbol = f"{asset['asset']}USDT"
        candidate = candidates.get(symbol)
        proposal = _rule_evaluate_position(
            settings,
            asset,
            candidate,
            float(portfolio.get("spot_capital_usdt") or 0),
            float(portfolio.get("total_value_usdt") or 0),
            buy_history,
        )
        if force_ai or _should_call_ai(settings, proposal):
            proposal.ai_called = True
            ai_calls += 1
            proposal.ai_opinion = await advisor.position_opinion(proposal.model_dump(mode="json"))
            proposal = _final_gate(settings, proposal)
        proposals.append(proposal)

    return {
        "portfolio_source": portfolio.get("source"),
        "spot_capital_usdt": portfolio.get("spot_capital_usdt"),
        "proposal_count": len(proposals),
        "ai_calls": ai_calls,
        "proposals": proposals,
    }


async def _candidate_map(settings: Settings, held_assets: list[dict]) -> dict:
    if not held_assets:
        return {}
    symbols = [f"{item['asset']}/USDT" for item in held_assets]
    try:
        candidates = await scan_okx_public(symbols) if settings.exchange_name.lower() == "okx" else []
    except Exception:
        candidates = []
    return {candidate.symbol: candidate for candidate in candidates}


def _rule_evaluate_position(
    settings: Settings,
    asset: dict,
    candidate,
    spot_capital_usdt: float = 0,
    total_value_usdt: float = 0,
    buy_history: list[dict] | None = None,
) -> PositionManagementProposal:
    pnl_pct = asset.get("pnl_pct")
    trend = candidate.trend_score if candidate else None
    liquidity = candidate.liquidity_score if candidate else None
    volatility = candidate.volatility_score if candidate else None
    metadata = candidate.metadata if candidate else {}
    support = metadata.get("support_usdt")
    resistance = metadata.get("resistance_usdt")
    drawdown = metadata.get("drawdown_from_resistance_pct")
    pattern = str(metadata.get("candlestick_pattern") or "").upper()
    pattern_bias = str(metadata.get("candlestick_bias") or "").lower()
    pattern_confidence = float(metadata.get("candlestick_confidence") or 0)
    bullish_pattern = pattern_bias == "bullish" and pattern_confidence >= 0.7
    bearish_pattern = pattern_bias == "bearish" and pattern_confidence >= 0.7
    position_weight = (float(asset.get("value_usdt") or 0) / total_value_usdt * 100) if total_value_usdt else None
    add_on_cooldown = _recent_buy_within_hours(asset["asset"], buy_history or [], settings.position_add_cooldown_hours)
    action = "HOLD"
    reason = "Holder-first: uu tien nam giu spot dai han."
    risks = []
    proposed_size_pct = None

    if pnl_pct is not None and pnl_pct >= settings.held_asset_take_profit_full_pct and trend is not None and trend < 0.35:
        action = "TAKE_PROFIT_FULL"
        reason = "PnL cao va trend suy yeu ro; chi tao de xuat, khong tu ban."
    elif pnl_pct is not None and pnl_pct >= settings.held_asset_take_profit_partial_pct and trend is not None and trend < 0.55:
        action = "TAKE_PROFIT_PARTIAL"
        reason = "PnL dat nguong va trend bat dau yeu; uu tien chot loi mot phan."
    elif pnl_pct is not None and pnl_pct <= settings.held_asset_exit_loss_pct and trend is not None and trend < 0.25:
        action = "HIGH_RISK_ALERT"
        reason = "Lo sau va trend dai hon suy yeu; chi canh bao rui ro cao, khong cat lo tu dong."
        risks.append("Khong tu cat lo; can rule va xac nhan rieng neu sau nay bat ban.")
    elif pnl_pct is not None and pnl_pct <= settings.held_asset_high_risk_loss_pct:
        action = "WATCH"
        reason = "Lo kha sau nhung trieth ly spot uu tien giu va theo doi."
    elif bearish_pattern and pnl_pct is not None and pnl_pct >= settings.held_asset_take_profit_partial_pct:
        action = "TAKE_PROFIT_PARTIAL"
        reason = f"Mo hinh nen {pattern} nghiêng giam; uu tien chot loi mot phan nhung van tôn trong holder-first."
    elif bearish_pattern and trend is not None and trend < 0.35:
        action = "WATCH"
        reason = f"Mo hinh nen {pattern} xau; theo doi sat, chua cat lo tu dong."
    elif volatility is not None and volatility > 0.80:
        action = "WATCH"
        reason = "Bien dong cao; theo doi sat, han che ban vi nhieu ngan han."
    elif spot_capital_usdt >= settings.min_new_trade_capital_usdt and trend is not None and liquidity is not None and (
        (trend >= 0.70 and liquidity >= 0.70) or (bullish_pattern and trend >= 0.58 and liquidity >= 0.60)
    ):
        if position_weight is not None and position_weight >= settings.position_max_asset_weight_pct:
            reason = "Coin tot nhung ty trong da cao; khong mua them."
            risks.append("Ty trong vuot nguong toi da.")
        elif add_on_cooldown:
            reason = "Coin tot nhung vua mua gan day; cho het cooldown mua them."
            risks.append("Dang trong cooldown mua them.")
        else:
            action = "CONSIDER_ADD"
            proposed_size_pct = 20.0
            reason = "Coin dang giu co trend/liquidity hoac mo hinh nen ho tro; co the can nhac mua them neu con von USDT."

    return PositionManagementProposal(
        symbol=f"{asset['asset']}USDT",
        asset=asset["asset"],
        quantity=float(asset.get("quantity") or 0),
        price_usdt=asset.get("price_usdt"),
        value_usdt=asset.get("value_usdt"),
        pnl_usdt=asset.get("pnl_usdt"),
        pnl_pct=pnl_pct,
        trend_score=trend,
        liquidity_score=liquidity,
        volatility_score=volatility,
        support_usdt=support,
        resistance_usdt=resistance,
        drawdown_from_resistance_pct=drawdown,
        position_weight_pct=position_weight,
        proposed_size_pct=proposed_size_pct,
        approval_status="requires_approval" if action != "HOLD" else "analysis_only",
        recommended_action=action,
        final_action=action,
        rule_reason=reason,
        risk_notes=risks,
    )


def _should_call_ai(settings: Settings, proposal: PositionManagementProposal) -> bool:
    if proposal.recommended_action != "HOLD":
        return True
    if proposal.pnl_pct is not None and abs(proposal.pnl_pct) >= settings.held_asset_strong_move_pct:
        return True
    if proposal.volatility_score is not None and proposal.volatility_score > 0.80:
        return True
    return False


def _final_gate(settings: Settings, proposal: PositionManagementProposal) -> PositionManagementProposal:
    opinion = proposal.ai_opinion
    if not opinion:
        return proposal
    ai_action = opinion.suggested_action
    if opinion.confidence < settings.position_ai_min_confidence:
        proposal.final_action = "HOLD" if proposal.recommended_action in {"TAKE_PROFIT_FULL", "HIGH_RISK_ALERT"} else proposal.recommended_action
        proposal.final_gate_passed = False
        proposal.risk_notes.append("AI confidence thap; Final Rule Gate giu hanh dong thuan trong.")
        return proposal
    if ai_action in {"TAKE_PROFIT_FULL", "HIGH_RISK_ALERT"}:
        if proposal.pnl_pct is None or proposal.pnl_pct > settings.held_asset_exit_loss_pct:
            proposal.final_action = "WATCH" if ai_action == "HIGH_RISK_ALERT" else "TAKE_PROFIT_PARTIAL"
            proposal.final_gate_passed = False
            proposal.risk_notes.append("Final Rule Gate chan ban/cat lo qua som theo trieth ly holder-first.")
            return proposal
    if ai_action == "CONSIDER_ADD":
        if proposal.trend_score is None or proposal.trend_score < 0.65 or proposal.liquidity_score is None or proposal.liquidity_score < 0.70:
            proposal.final_action = "HOLD"
            proposal.final_gate_passed = False
            proposal.risk_notes.append("Final Rule Gate chan mua them vi trend/liquidity chua du.")
            return proposal
        if proposal.position_weight_pct is not None and proposal.position_weight_pct >= settings.position_max_asset_weight_pct:
            proposal.final_action = "HOLD"
            proposal.final_gate_passed = False
            proposal.risk_notes.append("Final Rule Gate chan mua them vi ty trong coin da cao.")
            return proposal
    if ai_action == "TAKE_PROFIT_PARTIAL":
        proposal.proposed_size_pct = settings.position_partial_take_profit_pct
    if ai_action == "TAKE_PROFIT_FULL":
        proposal.proposed_size_pct = settings.position_full_take_profit_pct
    proposal.final_action = ai_action if ai_action else proposal.recommended_action
    proposal.approval_status = "requires_approval" if proposal.final_action != "HOLD" else "analysis_only"
    proposal.final_gate_passed = True
    return proposal

def _recent_buy_within_hours(asset: str, history: list[dict], hours: int) -> bool:
    if hours <= 0:
        return False
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    for item in history:
        symbol = str(item.get("symbol") or "").replace("-", "").replace("/", "").upper()
        item_asset = symbol[:-4] if symbol.endswith("USDT") else symbol
        created_at = item.get("created_at")
        if item_asset != asset or created_at is None:
            continue
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at >= cutoff:
            return True
    return False
