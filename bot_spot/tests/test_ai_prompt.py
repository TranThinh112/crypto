from spot_ai_bot.ai import POSITION_ACTIONS, _position_ai_payload, _position_ai_prompt


def test_position_ai_payload_only_sends_needed_fields():
    payload = _position_ai_payload(
        {
            "symbol": "BTCUSDT",
            "asset": "BTC",
            "pnl_pct": -0.4,
            "trend_score": 0.2,
            "liquidity_score": 1,
            "volatility_score": 0.09,
            "support_usdt": 64000,
            "resistance_usdt": 67000,
            "recommended_action": "HOLD",
            "rule_reason": "holder first",
            "created_at": "should_not_send",
            "ai_opinion": {"should": "not_send"},
            "approval_status": "should_not_send",
        }
    )

    assert payload["symbol"] == "BTCUSDT"
    assert payload["allowed_actions"] == POSITION_ACTIONS
    assert payload["decision_policy"]["default_action"] == "HOLD"
    assert "created_at" not in payload
    assert "ai_opinion" not in payload
    assert "approval_status" not in payload


def test_position_ai_prompt_is_strict_json_instruction():
    prompt = _position_ai_prompt(_position_ai_payload({"symbol": "BTCUSDT", "recommended_action": "HOLD"}))

    assert "Chỉ trả về một JSON object hợp lệ" in prompt
    assert "Schema bắt buộc" in prompt
    assert "ưu tiên nắm giữ coin tốt" in prompt
    assert "HOLD" in prompt
    assert "TAKE_PROFIT_FULL" in prompt
    assert "Dữ liệu tối thiểu" in prompt
    assert "Ã" not in prompt
