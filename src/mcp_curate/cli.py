"""Command-line entry point for mcp-curate.

Phase 1 wires up `parse` (inspect a spec) and `serve` (run the raw MCP
server over stdio). `curate` and `eval` land in later phases.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .curation.describer import DeterministicDescriber, LLMDescriber
from .curation.engine import DEFAULT_MAX_ACTIONS, DEFAULT_MAX_TOOLS, curate
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

    p_curate = sub.add_parser(
        "curate", help="show the before/after curation report for a spec"
    )
    p_curate.add_argument("spec", help="path to an OpenAPI 3.x JSON/YAML file")
    p_curate.add_argument(
        "--max-tools",
        type=int,
        default=DEFAULT_MAX_TOOLS,
        help=f"tool budget (default {DEFAULT_MAX_TOOLS})",
    )
    p_curate.add_argument(
        "--max-actions",
        type=int,
        default=DEFAULT_MAX_ACTIONS,
        help=f"split tools larger than this many actions (default {DEFAULT_MAX_ACTIONS})",
    )

    p_eval = sub.add_parser(
        "eval", help="A/B raw vs curated tool selection with your LLM key"
    )
    p_eval.add_argument("spec", help="path to an OpenAPI 3.x JSON/YAML file")
    p_eval.add_argument("--cases", required=True, help="golden cases YAML file")
    p_eval.add_argument(
        "--max-tools", type=int, default=DEFAULT_MAX_TOOLS, help="tool budget"
    )
    p_eval.add_argument(
        "--max-actions", type=int, default=DEFAULT_MAX_ACTIONS, help="split threshold"
    )
    p_eval.add_argument("--model", default=None, help="override the LLM model id")
    p_eval.add_argument(
        "--llm-descriptions",
        action="store_true",
        help="use the LLM to polish curated tool descriptions before evaluating",
    )

    p_serve = sub.add_parser("serve", help="serve an MCP server over stdio")
    p_serve.add_argument("spec", help="path to an OpenAPI 3.x JSON/YAML file")
    p_serve.add_argument(
        "--curated",
        action="store_true",
        help="serve the curated tool set instead of the raw one",
    )
    p_serve.add_argument(
        "--max-tools",
        type=int,
        default=DEFAULT_MAX_TOOLS,
        help=f"tool budget when --curated (default {DEFAULT_MAX_TOOLS})",
    )
    p_serve.add_argument(
        "--max-actions",
        type=int,
        default=DEFAULT_MAX_ACTIONS,
        help=f"split threshold when --curated (default {DEFAULT_MAX_ACTIONS})",
    )
    p_serve.add_argument(
        "--llm-descriptions",
        action="store_true",
        help="polish curated tool descriptions with the LLM (needs ANTHROPIC_API_KEY)",
    )
    p_serve.add_argument(
        "--base-url", default=None, help="override the spec's server URL"
    )
    p_serve.add_argument(
        "--allow-local-network",
        action="store_true",
        help="permit calls to localhost/private hosts (off by default for SSRF safety)",
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
        if args.command == "curate":
            return _cmd_curate(args)
        if args.command == "eval":
            return _cmd_eval(args)
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


def _cmd_curate(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    result = curate(spec, max_tools=args.max_tools, max_actions=args.max_actions)
    print(result.report.render())
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from .eval.harness import load_cases, run_eval
    from .eval.llm import DEFAULT_MODEL, AnthropicClient, LLMError

    spec = load_spec(args.spec)
    cases = load_cases(args.cases)
    try:
        client = AnthropicClient(model=args.model or DEFAULT_MODEL)
        describer = (
            LLMDescriber(client) if args.llm_descriptions else DeterministicDescriber()
        )
        report = run_eval(
            spec,
            cases,
            client,
            max_tools=args.max_tools,
            max_actions=args.max_actions,
            describer=describer,
        )
    except LLMError as exc:
        print(f"error: LLM request failed: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(report.render())
    return 0


def _build_describer(args: argparse.Namespace):
    if getattr(args, "llm_descriptions", False):
        from .eval.llm import DEFAULT_MODEL, AnthropicClient

        return LLMDescriber(AnthropicClient(model=DEFAULT_MODEL))
    return DeterministicDescriber()


def _cmd_serve(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec)
    if args.curated:
        describer = _build_describer(args)
        tools = curate(
            spec,
            max_tools=args.max_tools,
            max_actions=args.max_actions,
            describer=describer,
        ).curated_tools
        kind = "curated"
    else:
        tools = build_raw_tools(spec)
        kind = "raw"
    base_url = args.base_url if args.base_url is not None else spec.base_url
    server = ToolServer(
        name=spec.title,
        tools=tools,
        base_url=base_url,
        headers=_parse_headers(args.header),
        allow_local=args.allow_local_network,
    )
    print(
        f"serving {len(tools)} {kind} tools from {spec.title} over stdio",
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
