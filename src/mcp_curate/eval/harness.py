"""Run an A/B tool-selection eval: raw server vs curated server.

Each golden case names a natural-language ``request`` and the ``operation``
(operationId) that should ultimately handle it. The harness asks the LLM to
pick a tool from the *raw* set and from the *curated* set, then scores:

* raw selection      — did it pick the exact operation's tool?
* curated selection  — did it pick the meta-tool that contains the operation?
* curated end-to-end — did it pick the right meta-tool *and* the right action?

The headline comparison is raw-vs-curated selection accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..curation.describer import Describer
from ..curation.engine import curate
from ..parser.loader import load_spec
from ..parser.model import Spec
from ..server.builder import ACTION_KEY, ARGS_KEY, Tool, build_raw_tools
from .llm import LLMClient
from .report import CaseResult, EvalReport


@dataclass
class EvalCase:
    request: str
    operation_id: str
    # Optional expected arguments (param name -> value). When present, the
    # harness also scores whether the model constructed these correctly.
    arguments: dict[str, object] | None = None


def load_cases(path: str | Path) -> list[EvalCase]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    cases = data["cases"] if isinstance(data, dict) else data
    out: list[EvalCase] = []
    for item in cases:
        out.append(
            EvalCase(
                request=item["request"],
                operation_id=item["operation"],
                arguments=item.get("arguments"),
            )
        )
    return out


def _args_match(expected: dict[str, object], actual: dict[str, object]) -> bool:
    """Every expected key is present in `actual` with a matching value.

    Values are compared as case-folded strings so 42 == "42" and JSON-body
    nesting is tolerated: an expected key found anywhere in a nested body counts.
    """
    flat = _flatten(actual)
    for key, value in expected.items():
        if key not in flat:
            return False
        if str(flat[key]).strip().lower() != str(value).strip().lower():
            return False
    return True


def _flatten(obj: object, out: dict[str, object] | None = None) -> dict[str, object]:
    out = {} if out is None else out
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                _flatten(value, out)
            else:
                out.setdefault(key, value)
    elif isinstance(obj, list):
        for item in obj:
            _flatten(item, out)
    return out


def _raw_index(tools: list[Tool]) -> dict[str, str]:
    """operationId -> raw tool name."""
    return {tool.endpoint.operation_id: tool.name for tool in tools}


def _curated_index(tools: list[Tool]) -> dict[str, tuple[str, str]]:
    """operationId -> (meta-tool name, action)."""
    index: dict[str, tuple[str, str]] = {}
    for tool in tools:
        for action, endpoint in tool.operations.items():
            index[endpoint.operation_id] = (tool.name, action)
    return index


def run_eval(
    spec: Spec,
    cases: list[EvalCase],
    client: LLMClient,
    max_tools: int = 40,
    max_actions: int = 30,
    describer: Describer | None = None,
) -> EvalReport:
    from ..curation.sanitize import sanitize_tools

    raw_tools = build_raw_tools(spec)
    sanitize_tools(raw_tools)  # curated tools are already scrubbed by curate()
    curated_tools = curate(
        spec, max_tools=max_tools, max_actions=max_actions, describer=describer
    ).curated_tools

    raw_idx = _raw_index(raw_tools)
    cur_idx = _curated_index(curated_tools)

    results: list[CaseResult] = []
    skipped: list[str] = []
    for case in cases:
        if case.operation_id not in raw_idx or case.operation_id not in cur_idx:
            skipped.append(case.operation_id)
            continue

        expected_raw = raw_idx[case.operation_id]
        expected_tool, expected_action = cur_idx[case.operation_id]

        raw_pick = client.select(case.request, raw_tools)
        cur_pick = client.select(case.request, curated_tools)

        raw_name = raw_pick.name if raw_pick else None
        cur_name = cur_pick.name if cur_pick else None
        cur_action = cur_pick.arguments.get(ACTION_KEY) if cur_pick else None

        raw_ok = raw_name == expected_raw
        tool_ok = cur_name == expected_tool

        # Argument-construction scoring (only when the case declares expectations).
        has_args = bool(case.arguments)
        raw_arg_ok: bool | None = None
        cur_arg_ok: bool | None = None
        if has_args:
            raw_args = raw_pick.arguments if raw_pick else {}
            cur_args = cur_pick.arguments.get(ARGS_KEY, {}) if cur_pick else {}
            raw_arg_ok = raw_ok and _args_match(case.arguments, raw_args)
            cur_arg_ok = tool_ok and _args_match(case.arguments, cur_args)

        results.append(
            CaseResult(
                request=case.request,
                operation_id=case.operation_id,
                expected_raw=expected_raw,
                raw_pick=raw_name,
                raw_correct=raw_ok,
                expected_curated=expected_tool,
                expected_action=expected_action,
                curated_pick=cur_name,
                curated_action=cur_action,
                curated_correct=tool_ok,
                curated_action_correct=tool_ok and cur_action == expected_action,
                has_expected_args=has_args,
                raw_arg_correct=raw_arg_ok,
                curated_arg_correct=cur_arg_ok,
            )
        )

    return EvalReport(
        results=results,
        skipped=skipped,
        raw_tool_count=len(raw_tools),
        curated_tool_count=len(curated_tools),
    )
