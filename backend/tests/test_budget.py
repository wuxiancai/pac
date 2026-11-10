from decimal import Decimal

import pytest

from pac_poc.budget import (
    PRICE_VERSION,
    USD_CNY_RATE,
    UnknownPublicPrice,
    estimate_chat_cost,
)


def test_qwen_public_price_estimate_uses_cached_and_uncached_tokens() -> None:
    estimate = estimate_chat_cost(
        provider="qwen-app",
        model="qwen3.8-flash",
        prompt_text="unused",
        completion_text="unused",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_prompt_tokens=500_000,
    )

    assert estimate.amount_cny == Decimal("3.150000")
    assert estimate.method == "versioned-public-price"
    assert estimate.price_version == PRICE_VERSION
    assert estimate.exchange_rate_version is None


def test_deepseek_estimate_uses_peak_rate_and_versioned_cny_conversion() -> None:
    estimate = estimate_chat_cost(
        provider="deepseek",
        model="deepseek-flash",
        prompt_text="",
        completion_text="",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_prompt_tokens=0,
    )

    assert estimate.amount_cny == Decimal("10.080000")
    assert estimate.exchange_rate_version == "SAFE-2026-11-10"
    assert estimate.exchange_rate_version is not None
    assert USD_CNY_RATE > Decimal("6.7167")


def test_openrouter_reported_usd_cost_is_converted_but_remains_an_estimate() -> None:
    estimate = estimate_chat_cost(
        provider="openrouter",
        model="deepseek/deepseek-v4.1-flash-1017",
        prompt_text="",
        completion_text="",
        prompt_tokens=None,
        completion_tokens=None,
        cached_prompt_tokens=None,
        reported_cost=Decimal("0.5"),
        reported_currency="USD",
    )

    assert estimate.amount_cny == Decimal("3.360000")
    assert estimate.method == "provider-reported-cost-converted"
    assert estimate.exchange_rate_version == "SAFE-2026-11-10"


def test_missing_usage_estimates_tokens_from_characters_and_missing_models_fail_closed() -> None:
    estimate = estimate_chat_cost(
        provider="qwen-app",
        model="qwen3.8-flash",
        prompt_text="你好 PAC",
        completion_text="好",
        prompt_tokens=None,
        completion_tokens=None,
        cached_prompt_tokens=None,
    )
    assert (estimate.prompt_tokens, estimate.completion_tokens) == (6, 1)
    assert estimate.amount_cny == Decimal("0.000008")

    with pytest.raises(UnknownPublicPrice):
        estimate_chat_cost(
            provider="openrouter",
            model="unreviewed/model",
            prompt_text="x",
            completion_text="y",
            prompt_tokens=None,
            completion_tokens=None,
            cached_prompt_tokens=None,
        )


def test_invalid_usage_and_cost_currency_are_rejected() -> None:
    with pytest.raises(ValueError, match="cached_prompt_tokens"):
        estimate_chat_cost(
            provider="qwen-app",
            model="qwen3.8-flash",
            prompt_text="",
            completion_text="",
            prompt_tokens=1,
            completion_tokens=1,
            cached_prompt_tokens=2,
        )
    with pytest.raises(ValueError, match="currency"):
        estimate_chat_cost(
            provider="openrouter",
            model="deepseek/deepseek-v4.1-flash-1017",
            prompt_text="",
            completion_text="",
            prompt_tokens=0,
            completion_tokens=0,
            cached_prompt_tokens=0,
            reported_cost=Decimal("0.01"),
            reported_currency="CNY",
        )
