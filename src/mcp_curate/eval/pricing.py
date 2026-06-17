"""Token accounting and cost computation for the eval harness.

Token counts come straight from the Anthropic API response (`usage`) — they are
*measured*, not estimated. Cost is those exact token counts multiplied by the
model's published list price. Prices are USD per 1,000,000 tokens and can drift,
so they're overridable via env vars; verify against the current pricing page.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# (input $/1M, output $/1M) — list prices; override with MCP_CURATE_PRICE_IN/OUT.
_LIST_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}
_DEFAULT_PRICE = (3.0, 15.0)  # fall back to Sonnet-tier if model is unknown


@dataclass
class Usage:
    """Measured token usage, summable across requests."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    requests: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        self.requests += other.requests


def prices_for(model: str) -> tuple[float, float]:
    """(input, output) $/1M for a model, honoring env overrides."""
    in_env = os.environ.get("MCP_CURATE_PRICE_IN")
    out_env = os.environ.get("MCP_CURATE_PRICE_OUT")
    if in_env and out_env:
        return float(in_env), float(out_env)
    return _LIST_PRICES.get(model, _DEFAULT_PRICE)


def cost(model: str, usage: Usage) -> float:
    """USD cost of measured usage at the model's price (cache-aware)."""
    price_in, price_out = prices_for(model)
    return (
        usage.input_tokens / 1e6 * price_in
        + usage.output_tokens / 1e6 * price_out
        + usage.cache_read_tokens / 1e6 * price_in * 0.1      # cache reads ~0.1x
        + usage.cache_creation_tokens / 1e6 * price_in * 1.25  # cache writes ~1.25x
    )
