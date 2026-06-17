"""Export curated tools to a reusable file, and load them back.

`curate --export FILE` writes the curated tool set (including each tool's
backing operations) to JSON. `serve FILE` then runs that prebuilt set directly,
without re-curating — so an LLM-polished curation (`--llm-descriptions`) is paid
for once and reused for free on every later launch.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..parser.model import Endpoint, Parameter
from ..server.builder import Tool

EXPORT_KEY = "mcp_curate_export"
EXPORT_VERSION = "1"


def export_tools(path: str | Path, title: str, base_url: str, tools: list[Tool]) -> None:
    """Serialize a curated tool set to a self-contained JSON file."""
    data = {
        EXPORT_KEY: EXPORT_VERSION,
        "title": title,
        "base_url": base_url,
        "tools": [_tool_to_dict(t) for t in tools],
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_export_file(path: str | Path) -> bool:
    """True if `path` is a curate-export file (not a raw OpenAPI spec)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and EXPORT_KEY in data


def load_export(path: str | Path) -> tuple[str, str, list[Tool]]:
    """Reconstruct (title, base_url, tools) from a curate-export file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tools = [_tool_from_dict(t) for t in data.get("tools", [])]
    return data.get("title", "API"), data.get("base_url", ""), tools


def _tool_to_dict(tool: Tool) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "is_meta": tool.is_meta,
        "members": tool.members,
        "operations": {a: _endpoint_to_dict(e) for a, e in tool.operations.items()},
    }


def _tool_from_dict(d: dict) -> Tool:
    operations = {a: _endpoint_from_dict(e) for a, e in d["operations"].items()}
    return Tool(
        name=d["name"],
        description=d["description"],
        input_schema=d["input_schema"],
        operations=operations,
        is_meta=d.get("is_meta", False),
        members=d.get("members", []),
    )


def _endpoint_to_dict(e: Endpoint) -> dict:
    return {
        "operation_id": e.operation_id,
        "method": e.method,
        "path": e.path,
        "summary": e.summary,
        "description": e.description,
        "tags": e.tags,
        "parameters": [
            {
                "name": p.name,
                "location": p.location,
                "required": p.required,
                "schema": p.schema,
                "description": p.description,
            }
            for p in e.parameters
        ],
        "request_body": e.request_body,
        "request_body_required": e.request_body_required,
    }


def _endpoint_from_dict(d: dict) -> Endpoint:
    return Endpoint(
        operation_id=d["operation_id"],
        method=d["method"],
        path=d["path"],
        summary=d.get("summary", ""),
        description=d.get("description", ""),
        tags=d.get("tags", []),
        parameters=[
            Parameter(
                name=p["name"],
                location=p.get("location", "query"),
                required=p.get("required", False),
                schema=p.get("schema", {}),
                description=p.get("description", ""),
            )
            for p in d.get("parameters", [])
        ],
        request_body=d.get("request_body"),
        request_body_required=d.get("request_body_required", False),
    )
