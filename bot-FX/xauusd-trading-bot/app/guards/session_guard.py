"""Timezone-aware sessions, rollover and weekend controls."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config.settings import SessionConfig, SessionWindow
from app.strategy.trend_detector import RuleResult


def _parse(value: str) -> time:
    return time.fromisoformat(value)


def _inside(current: time, window: SessionWindow) -> bool:
    start, end = _parse(window.start), _parse(window.end)
    return start <= current <= end if start <= end else current >= start or current <= end


class SessionGuard:
    def __init__(self, config: SessionConfig) -> None:
        self.config = config
        self.timezone = ZoneInfo(config.timezone)

    def evaluate(self, now: datetime) -> tuple[bool, tuple[RuleResult, ...]]:
        local = now.astimezone(self.timezone)
        day = local.strftime("%A").upper()
        allowed_day = day in self.config.allowed_days
        allowed_session = any(_inside(local.time(), window) for window in self.config.allowed_sessions)
        rollover = self.config.avoid_rollover.enabled and _inside(local.time(), self.config.avoid_rollover)
        rules = (
            # The configured day list is authoritative. Forex configurations
            # omit weekends, while 24/7 crypto configurations may include them.
            RuleResult(allowed_day, "SESSION_ALLOWED_DAY", {"day": day}),
            RuleResult(allowed_session, "SESSION_ALLOWED_TIME", {"time": local.strftime("%H:%M"), "timezone": self.config.timezone}),
            RuleResult(not rollover, "SESSION_NOT_ROLLOVER", {"time": local.strftime("%H:%M")}),
        )
        return all(rule.passed for rule in rules), rules

    def entry_profile_rule(self, now: datetime, score: int) -> RuleResult:
        profile = self.config.entry_profile
        if not profile.enabled:
            return RuleResult(True, "ENTRY_SESSION_PROFILE_DISABLED", {})
        local = now.astimezone(self.timezone)
        active = any(_inside(local.time(), window) for window in profile.active_sessions)
        if active:
            return RuleResult(True, "ENTRY_ACTIVE_MARKET_SESSION", {
                "time": local.strftime("%H:%M"),
                "timezone": self.config.timezone,
                "mode": "NORMAL_ENTRY",
            })
        return RuleResult(score >= profile.quiet_minimum_signal_score, "QUIET_SESSION_STRONG_SIGNAL_REQUIRED", {
            "time": local.strftime("%H:%M"),
            "timezone": self.config.timezone,
            "score": score,
            "minimum": profile.quiet_minimum_signal_score,
            "mode": "REDUCED_ENTRY_FOCUS_ON_POSITION_MANAGEMENT",
        })

    def should_close_for_weekend(self, now: datetime) -> bool:
        if not self.config.close_before_weekend.enabled:
            return False
        local = now.astimezone(self.timezone)
        friday_cutoff = _parse(self.config.close_before_weekend.friday_close_time)
        return local.weekday() > 4 or (local.weekday() == 4 and local.time() >= friday_cutoff)
