"""Eval harness tests using a scripted, offline LLM client."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_curate.curation.engine import curate
from mcp_curate.eval.harness import (
    EvalCase,
    _args_match,
    _curated_index,
    _raw_index,
    load_cases,
    run_eval,
)
from mcp_curate.eval.llm import AnthropicClient, ToolPick
from mcp_curate.parser.loader import load_spec
from mcp_curate.server.builder import build_raw_tools

EXAMPLES = Path(__file__).parent.parent / "examples"
PETSTORE = EXAMPLES / "petstore.json"
CASES = EXAMPLES / "eval_cases" / "petstore.yaml"


class ScriptedClient:
    """Returns predetermined picks; distinguishes raw vs curated by is_meta."""

    def __init__(self, raw_map, cur_map):
        self.raw_map = raw_map
        self.cur_map = cur_map

    def select(self, request, tools):
        if tools and tools[0].is_meta:
            entry = self.cur_map.get(request)
            if entry is None:
                return None
            name, action = entry
            return ToolPick(name=name, arguments={"action": action})
        name = self.raw_map.get(request)
        return ToolPick(name=name, arguments={}) if name else None

    def complete(self, prompt):  # pragma: no cover - unused here
        return ""


def _expectations(spec, cases, max_tools=40):
    raw_idx = _raw_index(build_raw_tools(spec))
    cur_idx = _curated_index(curate(spec, max_tools=max_tools).curated_tools)
    raw_map = {c.request: raw_idx[c.operation_id] for c in cases}
    cur_map = {c.request: cur_idx[c.operation_id] for c in cases}
    return raw_map, cur_map


def test_load_cases():
    cases = load_cases(CASES)
    assert len(cases) >= 10
    assert all(c.request and c.operation_id for c in cases)


def test_indexes_cover_petstore():
    spec = load_spec(PETSTORE)
    raw_idx = _raw_index(build_raw_tools(spec))
    cur_idx = _curated_index(curate(spec).curated_tools)
    assert raw_idx["getPetById"] == "getPetById"
    tool_name, action = cur_idx["getPetById"]
    assert tool_name == "pet"
    assert action  # non-empty action name


def test_perfect_client_scores_full_marks():
    spec = load_spec(PETSTORE)
    cases = load_cases(CASES)
    raw_map, cur_map = _expectations(spec, cases)
    report = run_eval(spec, cases, ScriptedClient(raw_map, cur_map))
    assert report.raw_accuracy == 100.0
    assert report.curated_accuracy == 100.0
    assert report.curated_action_accuracy == 100.0


def test_wrong_client_scores_zero():
    spec = load_spec(PETSTORE)
    cases = load_cases(CASES)
    bad_raw = {c.request: "definitely_wrong" for c in cases}
    bad_cur = {c.request: ("definitely_wrong", "nope") for c in cases}
    report = run_eval(spec, cases, ScriptedClient(bad_raw, bad_cur))
    assert report.raw_accuracy == 0.0
    assert report.curated_accuracy == 0.0


def test_improvement_is_measured_and_rendered():
    """Raw mis-picks half the time; curated always routes correctly."""
    spec = load_spec(PETSTORE)
    cases = load_cases(CASES)
    raw_map, cur_map = _expectations(spec, cases)
    # Corrupt raw picks for every other case.
    degraded_raw = dict(raw_map)
    for i, c in enumerate(cases):
        if i % 2 == 0:
            degraded_raw[c.request] = "wrong_tool"
    report = run_eval(spec, cases, ScriptedClient(degraded_raw, cur_map))
    assert report.curated_accuracy > report.raw_accuracy
    text = report.render()
    assert "improvement:" in text
    assert "raw vs curated" in text


def test_skips_unknown_operation_ids():
    spec = load_spec(PETSTORE)
    cases = [EvalCase(request="bogus", operation_id="doesNotExist")]
    report = run_eval(spec, cases, ScriptedClient({}, {}))
    assert report.total == 0
    assert report.skipped == ["doesNotExist"]


def test_args_match_coerces_and_flattens():
    assert _args_match({"petId": 42}, {"petId": 42})
    assert _args_match({"petId": 42}, {"petId": "42"})  # string/int coercion
    assert not _args_match({"petId": 42}, {"petId": 7})
    assert not _args_match({"petId": 42}, {})  # missing key
    assert _args_match({"name": "x"}, {"body": {"name": "x"}})  # nested body


class ArgClient:
    """Returns correct tool + action and either correct or wrong arguments."""

    def __init__(self, raw_map, cur_map, arg_map, good=True):
        self.raw_map, self.cur_map, self.arg_map, self.good = raw_map, cur_map, arg_map, good

    def select(self, request, tools):
        args = dict(self.arg_map.get(request, {})) if self.good else {"petId": -1}
        if tools and tools[0].is_meta:
            name, action = self.cur_map[request]
            return ToolPick(name=name, arguments={"action": action, "arguments": args})
        return ToolPick(name=self.raw_map[request], arguments=args)

    def complete(self, prompt):  # pragma: no cover
        return ""


def test_argument_accuracy_scored_over_cases_with_expected_args():
    spec = load_spec(PETSTORE)
    cases = load_cases(CASES)
    raw_map, cur_map = _expectations(spec, cases)
    arg_map = {c.request: c.arguments for c in cases if c.arguments}
    assert arg_map  # the golden set declares some expected args

    good = run_eval(spec, cases, ArgClient(raw_map, cur_map, arg_map, good=True))
    assert good.raw_arg_accuracy == 100.0
    assert good.curated_arg_accuracy == 100.0
    assert "argument construction" in good.render()

    bad = run_eval(spec, cases, ArgClient(raw_map, cur_map, arg_map, good=False))
    assert bad.raw_arg_accuracy == 0.0
    assert bad.curated_arg_accuracy == 0.0
    # Tool selection still perfect even when args are wrong.
    assert bad.raw_accuracy == 100.0


def test_anthropic_client_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AnthropicClient(api_key=None)
