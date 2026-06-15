"""Server/builder tests, including a real stdio MCP client roundtrip."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_curate.parser.loader import load_spec
from mcp_curate.server.builder import BODY_KEY, build_input_schema, build_raw_tools

PETSTORE = Path(__file__).parent.parent / "examples" / "petstore.json"


def test_build_raw_tools_one_per_operation():
    spec = load_spec(PETSTORE)
    tools = build_raw_tools(spec)
    assert len(tools) == len(spec.endpoints)
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), "tool names must be unique"
    assert "getPetById" in names


def test_input_schema_marks_path_params_required():
    spec = load_spec(PETSTORE)
    get_pet = next(e for e in spec.endpoints if e.operation_id == "getPetById")
    schema = build_input_schema(get_pet)
    assert schema["type"] == "object"
    assert "petId" in schema["properties"]
    assert "petId" in schema["required"]


def test_input_schema_nests_request_body():
    spec = load_spec(PETSTORE)
    add_pet = next(e for e in spec.endpoints if e.operation_id == "addPet")
    schema = build_input_schema(add_pet)
    assert BODY_KEY in schema["properties"]


@pytest.mark.asyncio
async def test_stdio_server_lists_tools():
    """Spawn `mcp-curate serve` and list tools over the real MCP protocol."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_curate.cli", "serve", str(PETSTORE)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = {t.name for t in result.tools}
    assert "getPetById" in names
    assert len(names) == 19
