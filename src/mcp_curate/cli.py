"""Command-line entry point for mcp-curate.

Phase 1 wires up `parse` (inspect a spec) and `serve` (run the raw MCP
server over stdio). `curate` and `eval` land in later phases.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .parser.loader import SpecError, load_spec
from .server.builder import build_raw_tools
from .server.runtime import ToolServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-curate",
        description="Turn an OpenAPI spec into a high-quality MCP server.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="parse a spec and report tool counts")
    p_parse.add_argument("spec", help="path to an OpenAPI 3.x JSON/YAML file")

    p_serve = sub.add_parser("serve", help="serve the raw MCP server over stdio")
    p_serve.add_argument("spec", help="path to an OpenAPI 3.x JSON/YAML file")
    p_serve.add_argument(
        "--base-url", default=None, help="override the spec's server URL"
    )
    p_serve.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="KEY:VALUE",
        help="add an HTTP header to every request (repeatable; for auth)",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "parse":
            return _cmd_parse(args)
        if args.command == "serve":
            return _cmd_serve(args)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


def _cmd_parse(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    tools = build_raw_tools(spec)
    print(f"{spec.title} v{spec.version}")
    print(f"base url: {spec.base_url or '(none declared)'}")
    print(f"operations: {len(spec.endpoints)}")
    print(f"raw tools:  {len(tools)}")
    print("\nfirst tools:")
    for tool in tools[:10]:
        print(f"  - {tool.name}: {tool.description}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    tools = build_raw_tools(spec)
    base_url = args.base_url if args.base_url is not None else spec.base_url
    server = ToolServer(
        name=spec.title,
        tools=tools,
        base_url=base_url,
        headers=_parse_headers(args.header),
    )
    print(
        f"serving {len(tools)} raw tools from {spec.title} over stdio",
        file=sys.stderr,
    )
    asyncio.run(server.run())
    return 0


def _parse_headers(raw_headers: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in raw_headers:
        if ":" not in item:
            raise SpecError(f"bad --header {item!r}, expected KEY:VALUE")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


if __name__ == "__main__":
    raise SystemExit(main())
