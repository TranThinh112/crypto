from spot_ai_bot.ai import AIAdvisor
from spot_ai_bot.config import Settings


def test_ai_role_models_are_selected_from_role_settings():
    advisor = AIAdvisor(
        Settings(
            openai_api_key="fallback",
            openai_model="fallback-model",
            gpt_5_4_manager_api_key="manager-key",
            gpt_5_4_manager_model="manager-model",
            gpt_crypto_api_key="crypto-key",
            gpt_crypto_model="crypto-model",
            gpt_fork_api_key="fork-key",
            gpt_fork_model="fork-model",
        )
    )

    assert advisor._api_key_for_role("manager") == "manager-key"
    assert advisor._model_for_role("manager") == "manager-model"
    assert advisor._api_key_for_role("crypto") == "crypto-key"
    assert advisor._model_for_role("crypto") == "crypto-model"
    assert advisor._api_key_for_role("fork") == "fork-key"
    assert advisor._model_for_role("fork") == "fork-model"


def test_ai_role_falls_back_to_openai_key_when_role_key_empty():
    advisor = AIAdvisor(Settings(openai_api_key="fallback", openai_model="fallback-model"))

    assert advisor._api_key_for_role("manager") == "fallback"
    assert advisor._api_key_for_role("crypto") == "fallback"
    assert advisor._api_key_for_role("fork") == "fallback"


def test_ai_role_intended_responsibilities_are_documented_by_mapping():
    advisor = AIAdvisor(
        Settings(
            gpt_5_4_manager_api_key="manager-key",
            gpt_crypto_api_key="crypto-key",
            gpt_fork_api_key="fork-key",
        )
    )

    assert advisor._api_key_for_role("manager") == "manager-key"
    assert advisor._api_key_for_role("crypto") == "crypto-key"
    assert advisor._api_key_for_role("fork") == "fork-key"
