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


# Meta-tools select among their backing operations with this argument.
ACTION_KEY = "action"
ARGS_KEY = "arguments"


@dataclass
class Tool:
    """An MCP-facing tool backed by one or more OpenAPI operations.

    Raw tools back a single operation and expose its parameters flatly.
    Curated meta-tools (Phase 2) back several operations keyed by an
    ``action`` argument; ``is_meta`` selects how the runtime dispatches.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    # action name -> backing operation. Raw tools use the single key "".
    operations: dict[str, Endpoint]
    is_meta: bool = False
    # operationIds this tool consolidates (for the before/after report).
    members: list[str] = field(default_factory=list)

    @property
    def endpoint(self) -> Endpoint:
        """The sole backing operation (raw tools only)."""
        return next(iter(self.operations.values()))


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
                operations={"": endpoint},
                is_meta=False,
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


def meta_actions(endpoints: list[Endpoint], source_tags: list[str]) -> dict[str, Endpoint]:
    """Map short, unique action names to a group's backing operations.

    The group's tag prefix is stripped from each operationId (it's redundant
    inside a tool already named for the tag), then names are sanitized and
    de-duplicated. Order is preserved for stable output.
    """
    actions: dict[str, Endpoint] = {}
    used: set[str] = set()
    for endpoint in endpoints:
        base = _strip_tag_prefix(endpoint.operation_id, source_tags)
        name = _NAME_RE.sub("_", base).strip("_").lower() or "op"
        name = re.sub(r"_+", "_", name)
        actions[_unique_name(name, used)] = endpoint
    return actions


def build_meta_tool(
    name: str, description: str, actions: dict[str, Endpoint]
) -> Tool:
    """Assemble a meta-tool whose ``action`` argument selects an operation."""
    schema = {
        "type": "object",
        "properties": {
            ACTION_KEY: {
                "type": "string",
                "enum": list(actions),
                "description": "the operation to perform (see this tool's description)",
            },
            ARGS_KEY: {
                "type": "object",
                "description": "parameters for the chosen action",
                "additionalProperties": True,
            },
        },
        "required": [ACTION_KEY],
    }
    return Tool(
        name=name,
        description=description,
        input_schema=schema,
        operations=dict(actions),
        is_meta=True,
        members=[e.operation_id for e in actions.values()],
    )


def _strip_tag_prefix(operation_id: str, source_tags: list[str]) -> str:
    base = operation_id
    for tag in source_tags:
        tag_norm = _NAME_RE.sub("", tag).lower()
        for sep in ("_", "-", "/", "."):
            prefix = f"{tag}{sep}"
            if base.lower().startswith(prefix.lower()):
                return base[len(prefix):]
        # Also handle camelCase-ish "tagSomething" -> "Something".
        if tag_norm and base.lower().startswith(tag_norm) and len(base) > len(tag_norm):
            return base[len(tag_norm):]
    return base


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
