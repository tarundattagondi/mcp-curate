"""Produce LLM-friendly names and descriptions for curated tools.

Two strategies share one interface:

* :class:`DeterministicDescriber` (default) — fast, offline, reproducible. No
  API key required, so Phase 2 stays free and unit-testable.
* :class:`LLMDescriber` (``--llm-descriptions``) — asks an LLM to rewrite the
  lead sentence and tool name for clarity, falling back to the deterministic
  result on any error.

Either way, the per-action list is rendered deterministically and appended, so
the action names an LLM sees always match what the runtime actually dispatches.
"""

from __future__ import annotations

import re
from typing import Protocol

from ..parser.model import Endpoint
from .grouper import Group

_MAX_SUMMARY = 90


class Describer(Protocol):
    def describe(self, group: Group, actions: dict[str, Endpoint]) -> tuple[str, str]:
        """Return (tool_name, lead_sentence) for a group."""
        ...


def render_description(lead: str, actions: dict[str, Endpoint]) -> str:
    """Combine a lead sentence with the deterministic action list."""
    return f"{lead}\n\n{render_action_list(actions)}"


def render_action_list(actions: dict[str, Endpoint]) -> str:
    lines = ['Set "action" to one of:']
    for name, endpoint in actions.items():
        summary = (endpoint.summary or endpoint.description or "").strip().split("\n")[0]
        if len(summary) > _MAX_SUMMARY:
            summary = summary[: _MAX_SUMMARY - 1].rstrip() + "…"
        route = f"{endpoint.method.upper()} {endpoint.path}"
        lines.append(f"- {name}: {summary} ({route})" if summary else f"- {name}: {route}")
    lines.append('Pass the chosen action\'s parameters in "arguments".')
    return "\n".join(lines)


def tool_name_for(group: Group) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", group.key).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    return name[:64] or "tool"


class DeterministicDescriber:
    """Rule-based names/descriptions — no network, fully reproducible."""

    def describe(self, group: Group, actions: dict[str, Endpoint]) -> tuple[str, str]:
        name = tool_name_for(group)
        lead = (
            f"{group.title}: {len(actions)} related "
            f"operation{'s' if len(actions) != 1 else ''}."
        )
        return name, lead


class LLMDescriber:
    """LLM-polished lead sentence and tool name, with a safe fallback."""

    def __init__(self, client, model: str):
        self._client = client
        self._model = model
        self._fallback = DeterministicDescriber()

    def describe(self, group: Group, actions: dict[str, Endpoint]) -> tuple[str, str]:
        name, lead = self._fallback.describe(group, actions)
        try:
            sample = "\n".join(
                f"- {a}: {e.summary or e.path}" for a, e in list(actions.items())[:20]
            )
            prompt = (
                "You are naming one tool in an MCP server. The tool groups these "
                f"API operations:\n{sample}\n\n"
                "Reply with exactly two lines:\n"
                "name: <snake_case tool name, <=40 chars>\n"
                "lead: <one sentence, <=160 chars, says what the tool is for>"
            )
            text = self._client.complete(prompt, self._model)
            parsed = _parse_llm_reply(text)
            return parsed.get("name", name), parsed.get("lead", lead)
        except Exception:  # noqa: BLE001 — never let polishing break curation
            return name, lead


def _parse_llm_reply(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "name" and value:
            out["name"] = tool_name_for(Group(key=value, title=value, endpoints=[]))
        elif key == "lead" and value:
            out["lead"] = value
    return out
