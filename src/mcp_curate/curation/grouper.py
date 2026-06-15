"""Group related endpoints into candidate meta-tools.

The default strategy groups by OpenAPI tag, falling back to the first path
segment when an operation is untagged. Each group becomes one higher-level
tool whose ``action`` argument selects the underlying operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..parser.model import Endpoint, Spec

# Leading path segments that carry no grouping signal (e.g. /v1/, /api/).
# Stripping them keeps versioned APIs from collapsing into one giant group.
_VERSION_RE = re.compile(r"^(v\d+|\d+(\.\d+)*|api|rest)$", re.IGNORECASE)


def _meaningful_segments(path: str) -> list[str]:
    """Non-parameter path segments with leading version/api prefixes removed."""
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    i = 0
    while i < len(segments) and _VERSION_RE.match(segments[i]):
        i += 1
    return segments[i:]


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


def split_to_budget(
    groups: list[Group], max_actions: int, max_tools: int
) -> list[Group]:
    """Split oversized groups by path sub-segment, within the tool budget.

    A tag like ``repos`` with 200 operations becomes ``repos``,
    ``repos_actions``, ``repos_pulls`` … — each a focused tool. Splitting only
    spends the headroom between the current group count and ``max_tools``, and
    always targets the largest oversized group first, so a tight budget keeps
    tools clean rather than forcing unrelated merges.
    """
    if max_actions < 1:
        raise ValueError("max_actions must be >= 1")
    groups = list(groups)
    while len(groups) < max_tools:
        groups.sort(key=lambda g: (-g.size, g.key))
        progressed = False
        for i, group in enumerate(groups):
            if group.size <= max_actions:
                continue
            pieces = _split_once(group)
            if len(pieces) > 1 and len(groups) - 1 + len(pieces) <= max_tools:
                groups.pop(i)
                groups.extend(pieces)
                progressed = True
                break
        if not progressed:
            break
    groups.sort(key=lambda g: (-g.size, g.key))
    return groups


def _split_once(group: Group) -> list[Group]:
    """Split a group at the shallowest path depth that separates it."""
    tag = group.source_tags[0] if group.source_tags else group.key
    max_depth = max(
        (len(_distinguishing_segments(e.path, tag)) for e in group.endpoints),
        default=0,
    )
    for depth in range(max_depth):
        buckets: dict[str, list[Endpoint]] = {}
        for endpoint in group.endpoints:
            segments = _distinguishing_segments(endpoint.path, tag)
            sub = segments[depth] if depth < len(segments) else ""
            buckets.setdefault(sub, []).append(endpoint)
        if len(buckets) > 1:
            return [
                Group(
                    key=group.key if not sub else f"{group.key}_{sub}",
                    title=group.title if not sub else f"{group.title} / {sub}",
                    endpoints=endpoints,
                    source_tags=list(group.source_tags),
                )
                for sub, endpoints in buckets.items()
            ]
    return [group]


def dominant_segment(group: Group) -> str:
    """The most common meaningful leading path segment across a group."""
    counts: dict[str, int] = {}
    for endpoint in group.endpoints:
        segments = _meaningful_segments(endpoint.path)
        if segments:
            counts[segments[0]] = counts.get(segments[0], 0) + 1
    return max(counts, key=counts.get) if counts else group.key


def _distinguishing_segments(path: str, tag: str) -> list[str]:
    """Meaningful path segments, with leading tag-matching ones dropped."""
    segments = _meaningful_segments(path)
    i = 0
    while i < len(segments) and segments[i].lower() == tag.lower():
        i += 1
    return segments[i:]


def _group_key(endpoint: Endpoint) -> str:
    if endpoint.tags:
        return endpoint.tags[0]
    segments = _meaningful_segments(endpoint.path)
    return segments[0] if segments else "default"


def _titleize(key: str) -> str:
    words = re.split(r"[_\-/\s]+", key.strip())
    return " ".join(w.capitalize() for w in words if w) or key
