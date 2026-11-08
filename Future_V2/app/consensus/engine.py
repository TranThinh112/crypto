from typing import Literal

from app.schemas import AgentDecision, Consensus

WEIGHT_DOMAINS = {
    "TIDAL": ("trend", 0.20),
    "NORO": ("momentum", 0.15),
    "RUNE": ("regime", 0.15),
    "ZEPHR": ("liquidity", 0.10),
    "LUMEN": ("sentiment", 0.10),
    "OKAPI": ("portfolio", 0.10),
    "VESKA": ("execution", 0.10),
    "MARIN": ("critic", 0.10),
}
WEIGHTS = {agent: weight for agent, (_, weight) in WEIGHT_DOMAINS.items()}


def aggregate(votes: list[AgentDecision], symbol: str, threshold: float = 0.650) -> Consensus:
    if len(votes) != 8 or any(v.data_quality != "good" or v.veto for v in votes):
        reasons = ["invalid_or_veto"]
        for v in votes:
            if v.veto:
                for rc in (v.reason_codes or []):
                    if rc not in reasons:
                        reasons.append(rc)
                if not v.reason_codes:
                    reasons.append(f"{v.agent_name.lower()}_veto")
            elif v.data_quality != "good":
                reasons.append(f"{v.agent_name.lower()}_degraded")
        return Consensus(symbol=symbol, action="hold", score=0, approved=False, votes=votes, reason_codes=reasons)
    raw_score = sum(WEIGHTS[v.agent_name] * v.confidence * (1 if v.action in ("buy", "sell") else 0) for v in votes)
    actions = [v.action for v in votes]
    buy_count = actions.count("buy")
    sell_count = actions.count("sell")
    synergy_bonus = 0.10 if (buy_count == 8 or sell_count == 8) else 0.0
    score = min(1.0, round(raw_score + synergy_bonus, 4))
    action: Literal["buy", "sell", "hold"] = max(("buy", "sell"), key=actions.count) if score >= threshold else "hold"
    return Consensus(symbol=symbol, action=action, score=score, approved=score >= threshold and action != "hold", votes=votes, reason_codes=[])
