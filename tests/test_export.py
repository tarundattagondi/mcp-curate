"""Export a curated tool set and serve it back without re-curating."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_curate.curation.engine import curate
from mcp_curate.curation.export import (
    export_tools,
    is_export_file,
    load_export,
)
from mcp_curate.parser.loader import load_spec
from mcp_curate.server.builder import ACTION_KEY

PETSTORE = Path(__file__).parent.parent / "examples" / "petstore.json"


def test_export_round_trip_preserves_tools(tmp_path):
    spec = load_spec(PETSTORE)
    tools = curate(spec).curated_tools
    out = tmp_path / "curated.json"
    export_tools(out, spec.title, spec.base_url, tools)

    assert is_export_file(out)
    title, base_url, loaded = load_export(out)
    assert title == spec.title
    assert base_url == spec.base_url
    assert [t.name for t in loaded] == [t.name for t in tools]

    # Backing operations survive so the runtime can still build requests.
    orig = next(t for t in tools if t.name == "pet")
    back = next(t for t in loaded if t.name == "pet")
    assert set(back.operations) == set(orig.operations)
    assert back.is_meta == orig.is_meta
    assert ACTION_KEY in back.input_schema["properties"]


def test_is_export_file_rejects_raw_spec():
    assert not is_export_file(PETSTORE)


def test_malformed_export_fails_cleanly(tmp_path):
    from mcp_curate.parser.loader import SpecError

    bad = tmp_path / "bad.json"
    bad.write_text('{"mcp_curate_export": "1", "tools": [{"name": "x"}]}')  # missing fields
    with pytest.raises(SpecError):
        load_export(bad)

    not_export = tmp_path / "weird.json"
    not_export.write_text('{"mcp_curate_export": "1", "tools": "not-a-list"}')
    with pytest.raises(SpecError):
        load_export(not_export)


@pytest.mark.asyncio
async def test_serve_prebuilt_export_over_stdio(tmp_path):
    spec = load_spec(PETSTORE)
    out = tmp_path / "curated.json"
    export_tools(out, spec.title, spec.base_url, curate(spec).curated_tools)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_curate.cli", "serve", str(out)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    assert {t.name for t in result.tools} == {"pet", "store", "user"}
