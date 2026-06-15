"""Load and normalize an OpenAPI 3.x document into the internal model.

Handles JSON and YAML, resolves local ``$ref`` pointers with cycle detection
(large real-world specs such as GitHub's are deeply self-referential), and
flattens each operation into an :class:`Endpoint`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .model import Endpoint, Parameter, Spec

_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_MAX_REF_DEPTH = 50


class SpecError(ValueError):
    """Raised when a document is not a usable OpenAPI 3.x spec."""


def load_spec(path: str | Path) -> Spec:
    """Parse an OpenAPI 3.x file (JSON or YAML) into a :class:`Spec`."""
    path = Path(path)
    if not path.exists():
        raise SpecError(f"spec file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    doc = _parse_text(raw, path)

    if not isinstance(doc, dict):
        raise SpecError("top-level document is not an object")
    if not str(doc.get("openapi", "")).startswith("3."):
        raise SpecError(
            f"unsupported spec version: {doc.get('openapi')!r} (need OpenAPI 3.x)"
        )

    resolver = _RefResolver(doc)
    info = doc.get("info", {}) or {}
    spec = Spec(
        title=info.get("title", "API"),
        version=info.get("version", "0.0.0"),
        base_url=_base_url(doc),
    )

    seen_ids: set[str] = set()
    for path_str, path_item in (doc.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            endpoint = _build_endpoint(
                path_str, method.lower(), operation, shared_params, resolver, seen_ids
            )
            spec.endpoints.append(endpoint)

    if not spec.endpoints:
        raise SpecError("no operations found under `paths`")
    return spec


def _parse_text(raw: str, path: Path) -> Any:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(raw)
    if path.suffix.lower() == ".json":
        return json.loads(raw)
    # Unknown extension: try JSON first, fall back to YAML (a superset).
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return yaml.safe_load(raw)


def _base_url(doc: dict[str, Any]) -> str:
    servers = doc.get("servers") or []
    if servers and isinstance(servers[0], dict):
        return str(servers[0].get("url", "")).rstrip("/")
    return ""


def _build_endpoint(
    path: str,
    method: str,
    operation: dict[str, Any],
    shared_params: list[Any],
    resolver: "_RefResolver",
    seen_ids: set[str],
) -> Endpoint:
    operation_id = operation.get("operationId") or _synth_operation_id(method, path)
    operation_id = _dedupe(operation_id, seen_ids)

    params: list[Parameter] = []
    for raw_param in [*shared_params, *operation.get("parameters", [])]:
        param = resolver.resolve(raw_param)
        if not isinstance(param, dict) or "name" not in param:
            continue
        params.append(
            Parameter(
                name=param["name"],
                location=param.get("in", "query"),
                required=bool(param.get("required", False)),
                schema=resolver.resolve(param.get("schema", {})),
                description=param.get("description", ""),
            )
        )

    body_schema, body_required = _request_body(operation, resolver)

    return Endpoint(
        operation_id=operation_id,
        method=method,
        path=path,
        summary=operation.get("summary", ""),
        description=operation.get("description", ""),
        tags=list(operation.get("tags", []) or []),
        parameters=params,
        request_body=body_schema,
        request_body_required=body_required,
    )


def _request_body(
    operation: dict[str, Any], resolver: "_RefResolver"
) -> tuple[dict[str, Any] | None, bool]:
    body = resolver.resolve(operation.get("requestBody", {}))
    if not isinstance(body, dict):
        return None, False
    content = body.get("content", {}) or {}
    media = content.get("application/json")
    if not media:
        # Fall back to the first declared media type that carries a schema.
        media = next((m for m in content.values() if isinstance(m, dict)), None)
    if not isinstance(media, dict) or "schema" not in media:
        return None, False
    return resolver.resolve(media["schema"]), bool(body.get("required", False))


def _synth_operation_id(method: str, path: str) -> str:
    """Build a stable operationId for operations that omit one."""
    parts = re.findall(r"[a-zA-Z0-9]+", path)
    return "_".join([method, *parts]) or method


def _dedupe(operation_id: str, seen: set[str]) -> str:
    candidate = operation_id
    i = 2
    while candidate in seen:
        candidate = f"{operation_id}_{i}"
        i += 1
    seen.add(candidate)
    return candidate


class _RefResolver:
    """Resolves local ``$ref`` pointers, cutting cycles to keep output finite."""

    def __init__(self, doc: dict[str, Any]):
        self._doc = doc

    def resolve(self, node: Any, _seen: frozenset[str] = frozenset(), _depth: int = 0) -> Any:
        if _depth > _MAX_REF_DEPTH:
            return {}
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                if ref in _seen or not ref.startswith("#/"):
                    # Cycle, or an external ref we can't follow: stop here.
                    return {}
                target = self._lookup(ref)
                return self.resolve(target, _seen | {ref}, _depth + 1)
            return {
                k: self.resolve(v, _seen, _depth + 1)
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [self.resolve(item, _seen, _depth + 1) for item in node]
        return node

    def _lookup(self, ref: str) -> Any:
        node: Any = self._doc
        for token in ref.lstrip("#/").split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and token in node:
                node = node[token]
            else:
                return {}
        return node
