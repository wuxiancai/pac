"""Versioned, conservative public-price estimates for supported cloud chat models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


PRICE_VERSION = "2026-11-10"
USD_CNY_RATE_VERSION = "SAFE-2026-11-10"
USD_CNY_RATE = Decimal("6.72")  # SAFE midpoint 6.7167, rounded upward for estimation.
TOKENS_PER_MILLION = Decimal(1_000_000)
ESTIMATE_QUANTUM_CNY = Decimal("0.000001")


class UnknownPublicPrice(ValueError):
    """Raised when a provider/model pair has no reviewed price snapshot."""


@dataclass(frozen=True)
class PublicPrice:
    provider: str
    model: str
    currency: str
    uncached_input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    source_url: str
    schedule: str


@dataclass(frozen=True)
class CostEstimate:
    amount_cny: Decimal
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    price_version: str
    exchange_rate_version: str | None
    method: str


_PRICES = {
    ("deepseek", "deepseek-flash"): PublicPrice(
        provider="deepseek",
        model="deepseek-flash",
        currency="USD",
        uncached_input_per_million=Decimal("0.30"),
        cached_input_per_million=Decimal("0.006"),
        output_per_million=Decimal("1.20"),
        source_url="https://api-docs.deepseek.com/quick_start/pricing/",
        schedule="Peak rate; maximum public rate, independent of holiday calendar",
    ),
    ("openrouter", "deepseek/deepseek-v4.1-flash-1017"): PublicPrice(
        provider="openrouter",
        model="deepseek/deepseek-v4.1-flash-1017",
        currency="USD",
        uncached_input_per_million=Decimal("0.006"),
        cached_input_per_million=Decimal("0.005"),
        output_per_million=Decimal("0.50"),
        source_url="https://openrouter.ai/api/v1/models",
        schedule="Public model catalog snapshot; fixed model id",
    ),
    ("qwen-app", "qwen3.8-flash"): PublicPrice(
        provider="qwen-app",
        model="qwen3.8-flash",
        currency="CNY",
        uncached_input_per_million=Decimal("0.8"),
        cached_input_per_million=Decimal("0.1"),
        output_per_million=Decimal("2.7"),
        source_url="https://help.aliyun.com/zh/model-studio/qwen3-8-flash",
        schedule="China Beijing original price, excluding promotions",
    ),
}


def estimate_chat_cost(
    *,
    provider: str,
    model: str,
    prompt_text: str,
    completion_text: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_prompt_tokens: int | None,
    reported_cost: Decimal | None = None,
    reported_currency: str | None = None,
) -> CostEstimate:
    """Estimate CNY cost, substituting character counts for missing token usage.

    Character counts deliberately overestimate typical token counts and are marked
    estimated. The result is a budget estimate, never a claim of billed cost.
    """
    price = _PRICES.get((provider, model))
    if price is None:
        raise UnknownPublicPrice(f"no reviewed public price for {provider}/{model}")
    for name, value in (
        ("prompt_tokens", prompt_tokens),
        ("completion_tokens", completion_tokens),
        ("cached_prompt_tokens", cached_prompt_tokens),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{name} must be a non-negative integer or None")
    if cached_prompt_tokens is not None and prompt_tokens is not None:
        if cached_prompt_tokens > prompt_tokens:
            raise ValueError("cached_prompt_tokens cannot exceed prompt_tokens")

    if reported_cost is not None:
        if reported_cost < 0 or not reported_cost.is_finite():
            raise ValueError("reported cost must be finite and non-negative")
        if reported_currency != price.currency:
            raise ValueError("reported cost currency does not match the reviewed provider")
        if reported_currency == "USD":
            amount_cny = reported_cost * USD_CNY_RATE
            exchange_version: str | None = USD_CNY_RATE_VERSION
        else:
            amount_cny = reported_cost
            exchange_version = None
        # Provider request cost is still converted/estimated for the CNY budget.
        method = "provider-reported-cost-converted" if reported_currency == "USD" else "provider-reported-cost"
        resolved_prompt = prompt_tokens if prompt_tokens is not None else len(prompt_text)
        resolved_completion = (
            completion_tokens if completion_tokens is not None else len(completion_text)
        )
        resolved_cached = cached_prompt_tokens or 0
    else:
        # One character per token is a deliberately conservative fallback.
        resolved_prompt = prompt_tokens if prompt_tokens is not None else len(prompt_text)
        resolved_completion = (
            completion_tokens if completion_tokens is not None else len(completion_text)
        )
        resolved_cached = cached_prompt_tokens or 0
        if resolved_cached > resolved_prompt:
            raise ValueError("cached_prompt_tokens cannot exceed estimated prompt tokens")
        uncached_prompt = resolved_prompt - resolved_cached
        amount = (
            Decimal(uncached_prompt) * price.uncached_input_per_million
            + Decimal(resolved_cached) * price.cached_input_per_million
            + Decimal(resolved_completion) * price.output_per_million
        ) / TOKENS_PER_MILLION
        if price.currency == "USD":
            amount_cny = amount * USD_CNY_RATE
            exchange_version = USD_CNY_RATE_VERSION
        else:
            amount_cny = amount
            exchange_version = None
        method = "versioned-public-price"

    return CostEstimate(
        amount_cny=amount_cny.quantize(ESTIMATE_QUANTUM_CNY, rounding=ROUND_HALF_UP),
        prompt_tokens=resolved_prompt,
        completion_tokens=resolved_completion,
        cached_prompt_tokens=resolved_cached,
        price_version=PRICE_VERSION,
        exchange_rate_version=exchange_version,
        method=method,
    )
