"""Serve a set of :class:`Tool` objects as an MCP server over stdio.

The same runtime serves both the raw and the curated tool sets, so the eval
harness compares apples to apples. Tool calls are translated into real HTTP
requests against the spec's base URL; auth is bring-your-own via headers.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .builder import BODY_KEY, Tool


class ToolServer:
    """Wraps a tool set and exposes it over the MCP stdio transport."""

    def __init__(
        self,
        name: str,
        tools: list[Tool],
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self.name = name
        self.tools = {tool.name: tool for tool in tools}
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._server = Server(name)
        self._register()

    def _register(self) -> None:
        @self._server.list_tools()
        async def _list() -> list[types.Tool]:
            return [
                types.Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                )
                for tool in self.tools.values()
            ]

        @self._server.call_tool()
        async def _call(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
            tool = self.tools.get(name)
            if tool is None:
                return [types.TextContent(type="text", text=f"unknown tool: {name}")]
            result = await self._execute(tool, arguments or {})
            return [types.TextContent(type="text", text=result)]

    async def _execute(self, tool: Tool, arguments: dict[str, Any]) -> str:
        endpoint = tool.endpoint
        path = endpoint.path
        query: dict[str, Any] = {}
        headers = dict(self.headers)
        body: Any = None

        param_locations = {p.name: p.location for p in endpoint.parameters}
        for key, value in arguments.items():
            if key == BODY_KEY:
                body = value
                continue
            location = param_locations.get(key, "query")
            if location == "path":
                path = path.replace("{" + key + "}", quote(str(value), safe=""))
            elif location == "header":
                headers[key] = str(value)
            else:
                query[key] = value

        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    endpoint.method.upper(),
                    url,
                    params=query or None,
                    json=body if body is not None else None,
                    headers=headers,
                )
            return _format_response(response)
        except httpx.HTTPError as exc:
            return f"request failed: {exc}"

    async def run(self) -> None:
        async with stdio_server() as (read, write):
            await self._server.run(
                read, write, self._server.create_initialization_options()
            )


def _format_response(response: httpx.Response) -> str:
    head = f"HTTP {response.status_code}"
    try:
        return f"{head}\n{json.dumps(response.json(), indent=2)}"
    except (json.JSONDecodeError, ValueError):
        text = response.text
        return f"{head}\n{text[:4000]}"
