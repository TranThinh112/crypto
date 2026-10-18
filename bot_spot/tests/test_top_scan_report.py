from datetime import datetime, timezone

from spot_ai_bot.scheduler import _daily_report_no, _top_score_candidates


def test_daily_report_number_resets_by_vietnam_day_slots():
    assert _daily_report_no(datetime(2026, 7, 24, 17, 0, tzinfo=timezone.utc)) == 1
    assert _daily_report_no(datetime(2026, 7, 24, 21, 0, tzinfo=timezone.utc)) == 2
    assert _daily_report_no(datetime(2026, 7, 25, 13, 0, tzinfo=timezone.utc)) == 6


def test_top_score_candidates_sort_descending():
    items = [
        {"symbol": "A", "trend_score": 0.1, "liquidity_score": 0.1, "volatility_score": 0.9},
        {"symbol": "B", "trend_score": 0.8, "liquidity_score": 0.8, "volatility_score": 0.2},
    ]
    top = _top_score_candidates(items, limit=1)
    assert top[0]["symbol"] == "B"
    assert top[0]["composite_score"] > 0
