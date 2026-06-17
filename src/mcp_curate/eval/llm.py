"""LLM client used by the eval harness (and optional description rewriting).

The harness depends only on the :class:`LLMClient` protocol, so tests inject a
deterministic fake and real runs use :class:`AnthropicClient`. Bring-your-own
key: the Anthropic client reads ``ANTHROPIC_API_KEY`` from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from ..server.builder import Tool
from .pricing import Usage

DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMError(RuntimeError):
    """A user-facing LLM/API failure (billing, auth, rate limit, ...)."""


@dataclass
class ToolPick:
    """Which tool the model chose for a request, and with what arguments."""

    name: str
    arguments: dict[str, Any]
    usage: Usage | None = None  # measured token usage for this request, if known


class LLMClient(Protocol):
    def select(self, request: str, tools: list[Tool]) -> ToolPick | None:
        """Force the model to choose one tool for the request."""
        ...

    def complete(self, prompt: str) -> str:
        """Free-form completion (used by the optional LLM describer)."""
        ...


def _usage_of(message: Any) -> Usage:
    """Read measured token usage off an Anthropic response."""
    u = getattr(message, "usage", None)
    if u is None:
        return Usage(requests=1)
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        requests=1,
    )


def _to_api_tools(tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]


class AnthropicClient:
    """Real LLM client backed by the Anthropic Messages API."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "the eval harness needs the anthropic package: pip install 'mcp-curate[llm]'"
            ) from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("set ANTHROPIC_API_KEY to run the eval harness")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key)
        self._model = model

    def _create(self, **kwargs):
        """Call the Messages API, surfacing API failures as clean LLMErrors."""
        try:
            return self._client.messages.create(model=self._model, **kwargs)
        except self._anthropic.APIError as exc:
            message = getattr(exc, "message", None) or str(exc)
            raise LLMError(message) from exc

    def select(self, request: str, tools: list[Tool]) -> ToolPick | None:
        message = self._create(
            max_tokens=1024,
            tools=_to_api_tools(tools),
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": request}],
        )
        usage = _usage_of(message)
        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                return ToolPick(
                    name=block.name, arguments=dict(block.input or {}), usage=usage
                )
        return ToolPick(name="", arguments={}, usage=usage) if usage else None

    def complete(self, prompt: str) -> str:
        message = self._create(
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [b.text for b in message.content if getattr(b, "type", None) == "text"]
        return "".join(parts)
