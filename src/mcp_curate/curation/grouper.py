"""Group related endpoints into candidate meta-tools.

The default strategy groups by OpenAPI tag, falling back to the first path
segment when an operation is untagged. Each group becomes one higher-level
tool whose ``action`` argument selects the underlying operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..parser.model import Endpoint, Spec


@dataclass
class Group:
    """A set of endpoints that will collapse into a single meta-tool."""

    key: str
    title: str
    endpoints: list[Endpoint]
    # Original tags/segments folded in (grows when the budget merges groups).
    source_tags: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.endpoints)


def group_endpoints(spec: Spec) -> list[Group]:
    """Group a spec's endpoints by tag (path-segment fallback)."""
    buckets: dict[str, list[Endpoint]] = {}
    for endpoint in spec.endpoints:
        key = _group_key(endpoint)
        buckets.setdefault(key, []).append(endpoint)

    groups = [
        Group(key=key, title=_titleize(key), endpoints=eps, source_tags=[key])
        for key, eps in buckets.items()
    ]
    # Largest groups first: stable, and keeps the report readable.
    groups.sort(key=lambda g: (-g.size, g.key))
    return groups


def _group_key(endpoint: Endpoint) -> str:
    if endpoint.tags:
        return endpoint.tags[0]
    segments = [s for s in endpoint.path.split("/") if s and not s.startswith("{")]
    return segments[0] if segments else "default"


def _titleize(key: str) -> str:
    words = re.split(r"[_\-/\s]+", key.strip())
    return " ".join(w.capitalize() for w in words if w) or key
