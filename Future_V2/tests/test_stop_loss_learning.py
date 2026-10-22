import asyncio
import time
import pytest
from app.config import Settings
from app.consensus.engine import aggregate
from app.schemas import AgentDecision
from app.paper_worker import PaperWorker


def test_leverage_enforces_35x_minimum():
    settings = Settings(target_leverage=20, live_max_leverage=20)
    assert settings.target_leverage >= 35
    assert settings.live_max_leverage >= 50


def test_consensus_aggregates_veto_reason_codes():
    votes = [
        AgentDecision(agent_name="TIDAL", symbol="BNB-USDT", action="buy", confidence=0.9, suggested_position_pct=0.05),
        AgentDecision(agent_name="NORO", symbol="BNB-USDT", action="buy", confidence=0.9, suggested_position_pct=0.05),
        AgentDecision(agent_name="RUNE", symbol="BNB-USDT", action="hold", confidence=0.95, suggested_position_pct=0, veto=True, reason_codes=["similar_to_SL_01"]),
        AgentDecision(agent_name="ZEPHR", symbol="BNB-USDT", action="buy", confidence=0.85, suggested_position_pct=0.05),
        AgentDecision(agent_name="LUMEN", symbol="BNB-USDT", action="buy", confidence=0.8, suggested_position_pct=0.05),
        AgentDecision(agent_name="OKAPI", symbol="BNB-USDT", action="buy", confidence=0.85, suggested_position_pct=0.05),
        AgentDecision(agent_name="VESKA", symbol="BNB-USDT", action="buy", confidence=0.9, suggested_position_pct=0.05),
        AgentDecision(agent_name="MARIN", symbol="BNB-USDT", action="buy", confidence=0.85, suggested_position_pct=0.05),
    ]
    consensus = aggregate(votes, "BNB-USDT")
    assert not consensus.approved
    assert consensus.action == "hold"
    assert "invalid_or_veto" in consensus.reason_codes
    assert "similar_to_SL_01" in consensus.reason_codes


def test_stop_loss_memory_indexing_and_precheck():
    worker = PaperWorker(Settings(openai_api_key="key", enable_ai_advisory=False))

    class MockClient:
        api_key = "test_key"
        async def fills_history(self, symbol, limit=10):
            if "BNB" in symbol:
                return {
                    "data": [
                        {
                            "fillTime": int(time.time() * 1000 - 15 * 60 * 1000),  # 15 min ago
                            "fillPnl": "-0.657",
                            "fee": "-0.033",
                            "posSide": "long",
                            "side": "sell",
                            "fillPx": "741.2",
                        }
                    ]
                }
            return {"data": []}

    worker.client = MockClient()
    losses = asyncio.run(worker._get_recent_losses_memory())
    assert len(losses) >= 1
    case1 = losses[0]
    assert case1["case_id"] == "SL_01"
    assert case1["symbol"] == "BNB-USDT"
    assert case1["direction"] == "long"
    assert case1["exit_price"] == 741.2
    assert case1["net_loss_usdt"] < 0
    assert "SL_01" in case1["rule"]

    # Precheck should veto re-entering long on BNB within 30 min
    proposal = {"symbol": "BNB-USDT", "action": "buy", "data_quality": "good", "notional": 50, "target_margin_usdt": 3.5}
    orderbook = {"data_quality": "good"}
    portfolio = {"positions": {}, "available_cash": 10.0, "equity": 10.0}
    risk = {"data_quality": "good", "api_healthy": True, "liquidity_ok": True}

    reason = worker._ai_precheck_reason(proposal, portfolio, orderbook, risk)
    assert reason == "similar_to_SL_01"
