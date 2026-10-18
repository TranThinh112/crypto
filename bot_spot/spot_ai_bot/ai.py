import json

from openai import APIError, AuthenticationError
from openai import AsyncOpenAI

from spot_ai_bot.config import Settings
from spot_ai_bot.models import AdvisorOpinion, AllocationPlan, AssetGroup, MarketCandidate, PositionOpinion

POSITION_ACTIONS = [
    "HOLD",
    "WATCH",
    "CONSIDER_ADD",
    "TAKE_PROFIT_PARTIAL",
    "TAKE_PROFIT_FULL",
    "HIGH_RISK_ALERT",
]
POSITION_AI_FIELDS = [
    "symbol",
    "asset",
    "quantity",
    "price_usdt",
    "value_usdt",
    "pnl_usdt",
    "pnl_pct",
    "trend_score",
    "liquidity_score",
    "volatility_score",
    "support_usdt",
    "resistance_usdt",
    "drawdown_from_resistance_pct",
    "position_weight_pct",
    "recommended_action",
    "rule_reason",
    "risk_notes",
]


class AIAdvisor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def capital_allocation(self, total_budget: float) -> AllocationPlan:
        client = self._client_for_role("manager")
        if not client:
            return self._fallback_allocation(total_budget, "OPENAI_API_KEY is not configured.")

        prompt = (
            "Allocate this fixed user budget between crypto, stocks, commodities, and cash. "
            "Return strict JSON with keys allocation and reason. The sum must equal the budget. "
            f"Budget: {total_budget} USD."
        )
        try:
            response = await client.chat.completions.create(
                model=self._model_for_role("manager"),
                temperature=self.settings.ai_temperature,
                messages=[
                    {"role": "system", "content": "You are a cautious portfolio allocation advisor. You do not trade directly."},
                    {"role": "user", "content": prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content or "{}")
            return AllocationPlan(total_budget_usd=total_budget, allocation=data["allocation"], reason=data["reason"])
        except (APIError, AuthenticationError, json.JSONDecodeError, KeyError, TypeError) as exc:
            return self._fallback_allocation(total_budget, f"AI allocation fallback after provider error: {type(exc).__name__}.")

    async def group_opinion(self, candidate: MarketCandidate) -> AdvisorOpinion:
        role = "crypto" if candidate.group == AssetGroup.crypto else "fork" if candidate.group == AssetGroup.commodities else "manager"
        client = self._client_for_role(role)
        if not client:
            return AdvisorOpinion(
                group=candidate.group,
                symbol=candidate.symbol,
                opinion="neutral_to_bullish" if candidate.trend_score >= 0.65 else "neutral",
                confidence=min(0.85, max(0.2, candidate.trend_score)),
                suggested_action="consider_buy" if candidate.trend_score >= 0.65 else "wait",
                reason="Fallback advisor based on trend/liquidity scores because OPENAI_API_KEY is not configured.",
                risks=["AI API is not configured", "Use paper mode until live rules are verified"],
            )

        try:
            response = await client.chat.completions.create(
                model=self._model_for_role(role),
                temperature=self.settings.ai_temperature,
                messages=[
                    {"role": "system", "content": "You are an advisor only. You never directly decide or execute trades. Return strict JSON."},
                    {"role": "user", "content": f"Give an advisor opinion for this spot candidate: {candidate.model_dump_json()}"},
                ],
            )
            data = json.loads(response.choices[0].message.content or "{}")
            return AdvisorOpinion(**data)
        except (APIError, AuthenticationError, json.JSONDecodeError, TypeError, ValueError):
            return self._fallback_opinion(candidate, "AI advisor fallback after provider error.")

    async def position_opinion(self, position: dict) -> PositionOpinion:
        symbol = str(position.get("symbol") or "")
        fallback_action = str(position.get("recommended_action") or "HOLD")
        client = self._client_for_role("crypto")
        if not client:
            return PositionOpinion(
                symbol=symbol,
                opinion="holder_first_fallback",
                confidence=0.55,
                suggested_action=fallback_action,
                reason="Fallback advisor: uu tien nam giu spot dai han va chi canh bao khi rule thay rui ro lon.",
                risks=["OPENAI_API_KEY is not configured"],
            )

        prompt = _position_ai_prompt(_position_ai_payload(position))
        try:
            response = await client.chat.completions.create(
                model=self._model_for_role("crypto"),
                temperature=self.settings.ai_temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an advisor only. Final rules decide after you. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content or "{}")
            if data.get("suggested_action") not in POSITION_ACTIONS:
                raise ValueError("Invalid suggested_action")
            return PositionOpinion(**data)
        except (APIError, AuthenticationError, json.JSONDecodeError, TypeError, ValueError):
            return PositionOpinion(
                symbol=symbol,
                opinion="ai_position_fallback",
                confidence=0.50,
                suggested_action=fallback_action,
                reason="AI provider unavailable or returned invalid JSON; fallback to holder-first rules.",
                risks=["AI provider is unavailable"],
            )

    def _client_for_role(self, role: str) -> AsyncOpenAI | None:
        api_key = self._api_key_for_role(role)
        return AsyncOpenAI(api_key=api_key) if api_key else None

    def _api_key_for_role(self, role: str) -> str:
        if role == "manager" and self.settings.gpt_5_4_manager_enabled:
            return self.settings.gpt_5_4_manager_api_key or self.settings.openai_api_key
        if role == "crypto" and self.settings.gpt_crypto_enabled:
            return self.settings.gpt_crypto_api_key or self.settings.openai_api_key
        if role == "fork" and self.settings.gpt_fork_enabled:
            return self.settings.gpt_fork_api_key or self.settings.openai_api_key
        return self.settings.openai_api_key

    def _model_for_role(self, role: str) -> str:
        if role == "manager" and self.settings.gpt_5_4_manager_enabled:
            return self.settings.gpt_5_4_manager_model or self.settings.openai_model
        if role == "crypto" and self.settings.gpt_crypto_enabled:
            return self.settings.gpt_crypto_model or self.settings.openai_model
        if role == "fork" and self.settings.gpt_fork_enabled:
            return self.settings.gpt_fork_model or self.settings.openai_model
        return self.settings.openai_model

    def _fallback_allocation(self, total_budget: float, reason: str) -> AllocationPlan:
        return AllocationPlan(
            total_budget_usd=total_budget,
            allocation={
                AssetGroup.crypto: round(total_budget * 0.45, 2),
                AssetGroup.stocks: round(total_budget * 0.30, 2),
                AssetGroup.commodities: round(total_budget * 0.15, 2),
                AssetGroup.cash: round(total_budget * 0.10, 2),
            },
            reason=reason,
        )

    def _fallback_opinion(self, candidate: MarketCandidate, reason: str) -> AdvisorOpinion:
        return AdvisorOpinion(
            group=candidate.group,
            symbol=candidate.symbol,
            opinion="neutral_to_bullish" if candidate.trend_score >= 0.65 else "neutral",
            confidence=min(0.85, max(0.2, candidate.trend_score)),
            suggested_action="consider_buy" if candidate.trend_score >= 0.65 else "wait",
            reason=reason,
            risks=["AI provider is unavailable", "Use paper mode until live rules are verified"],
        )

def _position_ai_payload(position: dict) -> dict:
    payload = {key: position.get(key) for key in POSITION_AI_FIELDS if key in position}
    payload["allowed_actions"] = POSITION_ACTIONS
    payload["decision_policy"] = {
        "default_action": "HOLD",
        "holder_first": True,
        "do_not_execute": True,
        "avoid_short_term_panic_sell": True,
        "cut_loss_requires_structural_risk": True,
    }
    return payload

def _position_ai_prompt(payload: dict) -> str:
    schema = {
        "symbol": "string",
        "opinion": "string",
        "confidence": "number between 0 and 1",
        "suggested_action": POSITION_ACTIONS,
        "reason": "string",
        "risks": ["string"],
    }
    return (
        _vi("Nhiem vu: danh gia vi the spot dang nam giu. ")
        + _vi("Ban chi la co van, khong duoc quyet dinh cuoi cung va khong duoc thuc thi lenh. ")
        + _vi("He thong rule se kiem tra lai sau khi ban dua y kien. ")
        + _vi("Chi tra ve mot JSON object hop le, khong markdown, khong viet them giai thich ngoai JSON. ")
        + _vi("Schema bat buoc: ")
        + f"{json.dumps(schema, ensure_ascii=False)}. "
        + _vi("Nguyen tac giao dich spot dai han: uu tien nam giu coin tot; neu khong chac chan thi chon HOLD; ")
        + _vi("khong khuyen nghi ban hoac cat lo chi vi bien dong ngan han; ")
        + _vi("TAKE_PROFIT_FULL hoac HIGH_RISK_ALERT chi duoc dung khi co rui ro dai han hoac rui ro cau truc ro rang; ")
        + _vi("CONSIDER_ADD chi duoc dung khi trend va thanh khoan tot, dong thoi du lieu rule ung ho. ")
        + _vi("Du lieu toi thieu can danh gia: ")
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )

def _vi(text: str) -> str:
    translations = {
        "Nhiem vu: danh gia vi the spot dang nam giu. ": "Nhi\u1ec7m v\u1ee5: \u0111\u00e1nh gi\u00e1 v\u1ecb th\u1ebf spot \u0111ang n\u1eafm gi\u1eef. ",
        "Ban chi la co van, khong duoc quyet dinh cuoi cung va khong duoc thuc thi lenh. ": "B\u1ea1n ch\u1ec9 l\u00e0 c\u1ed1 v\u1ea5n, kh\u00f4ng \u0111\u01b0\u1ee3c quy\u1ebft \u0111\u1ecbnh cu\u1ed1i c\u00f9ng v\u00e0 kh\u00f4ng \u0111\u01b0\u1ee3c th\u1ef1c thi l\u1ec7nh. ",
        "He thong rule se kiem tra lai sau khi ban dua y kien. ": "H\u1ec7 th\u1ed1ng rule s\u1ebd ki\u1ec3m tra l\u1ea1i sau khi b\u1ea1n \u0111\u01b0a \u00fd ki\u1ebfn. ",
        "Chi tra ve mot JSON object hop le, khong markdown, khong viet them giai thich ngoai JSON. ": "Ch\u1ec9 tr\u1ea3 v\u1ec1 m\u1ed9t JSON object h\u1ee3p l\u1ec7, kh\u00f4ng markdown, kh\u00f4ng vi\u1ebft th\u00eam gi\u1ea3i th\u00edch ngo\u00e0i JSON. ",
        "Schema bat buoc: ": "Schema b\u1eaft bu\u1ed9c: ",
        "Nguyen tac giao dich spot dai han: uu tien nam giu coin tot; neu khong chac chan thi chon HOLD; ": "Nguy\u00ean t\u1eafc giao d\u1ecbch spot d\u00e0i h\u1ea1n: \u01b0u ti\u00ean n\u1eafm gi\u1eef coin t\u1ed1t; n\u1ebfu kh\u00f4ng ch\u1eafc ch\u1eafn th\u00ec ch\u1ecdn HOLD; ",
        "khong khuyen nghi ban hoac cat lo chi vi bien dong ngan han; ": "kh\u00f4ng khuy\u1ebfn ngh\u1ecb b\u00e1n ho\u1eb7c c\u1eaft l\u1ed7 ch\u1ec9 v\u00ec bi\u1ebfn \u0111\u1ed9ng ng\u1eafn h\u1ea1n; ",
        "TAKE_PROFIT_FULL hoac HIGH_RISK_ALERT chi duoc dung khi co rui ro dai han hoac rui ro cau truc ro rang; ": "TAKE_PROFIT_FULL ho\u1eb7c HIGH_RISK_ALERT ch\u1ec9 \u0111\u01b0\u1ee3c d\u00f9ng khi c\u00f3 r\u1ee7i ro d\u00e0i h\u1ea1n ho\u1eb7c r\u1ee7i ro c\u1ea5u tr\u00fac r\u00f5 r\u00e0ng; ",
        "CONSIDER_ADD chi duoc dung khi trend va thanh khoan tot, dong thoi du lieu rule ung ho. ": "CONSIDER_ADD ch\u1ec9 \u0111\u01b0\u1ee3c d\u00f9ng khi trend v\u00e0 thanh kho\u1ea3n t\u1ed1t, \u0111\u1ed3ng th\u1eddi d\u1eef li\u1ec7u rule \u1ee7ng h\u1ed9. ",
        "Du lieu toi thieu can danh gia: ": "D\u1eef li\u1ec7u t\u1ed1i thi\u1ec3u c\u1ea7n \u0111\u00e1nh gi\u00e1: ",
    }
    return translations[text]
