"""Spec-agnostic internal model.

The parser converts an OpenAPI document into these dataclasses so the rest of
the codebase never has to know about OpenAPI's shape. The curation engine
(Phase 2) and the server builder both operate on ``Endpoint`` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParamLocation = Literal["path", "query", "header", "cookie"]


@dataclass
class Parameter:
    """A single operation parameter (path/query/header/cookie)."""

    name: str
    location: ParamLocation
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class Endpoint:
    """One OpenAPI operation, flattened and self-contained."""

    operation_id: str
    method: str  # lowercase: get/post/put/patch/delete
    path: str  # e.g. /pets/{petId}
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    # Resolved JSON schema for an application/json request body, or None.
    request_body: dict[str, Any] | None = None
    request_body_required: bool = False

    @property
    def primary_tag(self) -> str:
        """First tag, or 'default' if the operation declares none."""
        return self.tags[0] if self.tags else "default"


@dataclass
class Spec:
    """A parsed OpenAPI document reduced to what we need."""

    title: str
    version: str
    base_url: str
    endpoints: list[Endpoint] = field(default_factory=list)
