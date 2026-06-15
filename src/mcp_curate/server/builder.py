"""Build MCP tool definitions from parsed endpoints.

Phase 1 produces a raw, one-tool-per-operation mapping. Phase 2's curation
engine produces a smaller set of these same :class:`Tool` objects, so keeping
this representation stable lets the same runtime serve either set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..parser.model import Endpoint, Spec

# MCP tool names must be reasonably short identifiers.
_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME_LEN = 64

# JSON-schema key the request body is nested under, to avoid colliding with
# path/query/header parameter names.
BODY_KEY = "body"


@dataclass
class Tool:
    """An MCP-facing tool backed by one OpenAPI operation (raw mapping)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    endpoint: Endpoint
    # Names this tool consolidates (Phase 2 fills this; raw tools list themselves).
    members: list[str] = field(default_factory=list)


def build_raw_tools(spec: Spec) -> list[Tool]:
    """One tool per operation — the naive baseline curation improves upon."""
    tools: list[Tool] = []
    used: set[str] = set()
    for endpoint in spec.endpoints:
        name = _unique_name(_tool_name(endpoint), used)
        tools.append(
            Tool(
                name=name,
                description=_raw_description(endpoint),
                input_schema=build_input_schema(endpoint),
                endpoint=endpoint,
                members=[endpoint.operation_id],
            )
        )
    return tools


def build_input_schema(endpoint: Endpoint) -> dict[str, Any]:
    """Combine path/query/header params and JSON body into one JSON schema."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in endpoint.parameters:
        if param.location not in ("path", "query", "header"):
            continue
        schema = dict(param.schema) if isinstance(param.schema, dict) else {}
        if param.description and "description" not in schema:
            schema["description"] = param.description
        properties[param.name] = schema or {"type": "string"}
        if param.required or param.location == "path":
            required.append(param.name)

    if endpoint.request_body is not None:
        body = endpoint.request_body
        if isinstance(body, dict) and not body.get("description"):
            body = {**body, "description": "JSON request body."}
        properties[BODY_KEY] = body
        if endpoint.request_body_required:
            required.append(BODY_KEY)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _tool_name(endpoint: Endpoint) -> str:
    base = endpoint.operation_id or f"{endpoint.method}_{endpoint.path}"
    name = _NAME_RE.sub("_", base).strip("_")
    name = re.sub(r"_+", "_", name)
    return name[:_MAX_NAME_LEN] or "op"


def _unique_name(name: str, used: set[str]) -> str:
    candidate = name
    i = 2
    while candidate in used:
        suffix = f"_{i}"
        candidate = name[: _MAX_NAME_LEN - len(suffix)] + suffix
        i += 1
    used.add(candidate)
    return candidate


def _raw_description(endpoint: Endpoint) -> str:
    text = endpoint.summary or endpoint.description or ""
    text = text.strip().split("\n")[0]
    route = f"{endpoint.method.upper()} {endpoint.path}"
    return f"{text} ({route})" if text else route
