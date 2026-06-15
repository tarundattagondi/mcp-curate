"""Curation engine tests: grouping, budget, describer, dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_curate.curation.budget import enforce_budget
from mcp_curate.curation.describer import DeterministicDescriber, render_action_list
from mcp_curate.curation.engine import curate
from mcp_curate.curation.grouper import Group, group_endpoints
from mcp_curate.parser.loader import load_spec
from mcp_curate.parser.model import Endpoint
from mcp_curate.server.builder import ACTION_KEY, build_meta_tool, meta_actions
from mcp_curate.server.runtime import ToolServer

EXAMPLES = Path(__file__).parent.parent / "examples"
PETSTORE = EXAMPLES / "petstore.json"


def _fake_groups(sizes: dict[str, int]) -> list[Group]:
    groups = []
    for key, n in sizes.items():
        eps = [
            Endpoint(operation_id=f"{key}_{i}", method="get", path=f"/{key}/{i}", tags=[key])
            for i in range(n)
        ]
        groups.append(Group(key=key, title=key, endpoints=eps, source_tags=[key]))
    return groups


def test_group_endpoints_by_tag():
    spec = load_spec(PETSTORE)
    groups = {g.key: g.size for g in group_endpoints(spec)}
    assert groups == {"pet": 8, "user": 7, "store": 4}


def test_enforce_budget_merges_smallest_first():
    groups = _fake_groups({"big": 50, "mid": 10, "small": 2, "tiny": 1})
    out, merges = enforce_budget(groups, max_tools=2)
    assert len(out) == 2
    # The two smallest (tiny, small) should have merged, big stays alone.
    keys = {g.key for g in out}
    assert "big" in keys
    assert merges  # at least one merge recorded
    merged = next(g for g in out if g.key != "big" and g.size != 50)
    assert merged.size <= 13  # mid+small+tiny folded together, not big


def test_enforce_budget_noop_under_budget():
    groups = _fake_groups({"a": 3, "b": 2})
    out, merges = enforce_budget(groups, max_tools=40)
    assert len(out) == 2
    assert merges == []


def test_meta_actions_strip_tag_prefix_and_dedupe():
    eps = [
        Endpoint(operation_id="repos_get", method="get", path="/repos/{x}", tags=["repos"]),
        Endpoint(operation_id="repos_get", method="get", path="/repos/{y}", tags=["repos"]),
        Endpoint(operation_id="repos-list", method="get", path="/repos", tags=["repos"]),
    ]
    actions = meta_actions(eps, ["repos"])
    names = list(actions)
    assert "get" in names
    assert "list" in names
    assert len(names) == len(set(names)) == 3  # duplicate "get" de-duplicated


def test_render_action_list_includes_route():
    ep = Endpoint(operation_id="getX", method="get", path="/x/{id}", summary="Get X", tags=["x"])
    text = render_action_list({"get_x": ep})
    assert "get_x" in text
    assert "GET /x/{id}" in text


def test_curate_petstore_three_tools():
    spec = load_spec(PETSTORE)
    result = curate(spec, max_tools=40)
    assert len(result.curated_tools) == 3
    names = {t.name for t in result.curated_tools}
    assert names == {"pet", "store", "user"}
    assert result.report.raw_count == 19
    assert all(t.is_meta for t in result.curated_tools)


def test_curate_respects_budget():
    spec = load_spec(PETSTORE)
    result = curate(spec, max_tools=2)
    assert len(result.curated_tools) == 2
    assert result.report.curated_count == 2


def test_meta_tool_dispatch_builds_correct_request():
    spec = load_spec(PETSTORE)
    pet = next(g for g in group_endpoints(spec) if g.key == "pet")
    actions = meta_actions(pet.endpoints, pet.source_tags)
    tool = build_meta_tool("pet", "Pet ops", actions)
    server = ToolServer("t", [tool], base_url="https://api.example.com")

    action = next(a for a, e in actions.items() if e.operation_id == "getPetById")
    endpoint = tool.operations[action]
    method, url, query, body, _ = server._build_request(endpoint, {"petId": 42})
    assert method == "GET"
    assert url == "https://api.example.com/pet/42"
    assert query == {}


@pytest.mark.asyncio
async def test_curated_server_lists_meta_tools_over_stdio():
    import sys

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_curate.cli", "serve", "--curated", str(PETSTORE)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    by_name = {t.name: t for t in result.tools}
    assert set(by_name) == {"pet", "store", "user"}
    assert ACTION_KEY in by_name["pet"].inputSchema["properties"]
    assert "enum" in by_name["pet"].inputSchema["properties"][ACTION_KEY]
