"""Trim a set of groups down to a tool budget by merging the smallest.

Cursor and other clients cap the number of tools they will surface (~40 is a
common, conservative default). When tag-based grouping yields more groups than
the budget allows, we repeatedly merge the two smallest groups — small,
miscellaneous groups are the least costly to combine and the merge is recorded
for the before/after report.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grouper import Group, _titleize


@dataclass
class Merge:
    """One merge event: several source groups folded into a result group."""

    result_key: str
    source_keys: list[str]
    size: int


def enforce_budget(
    groups: list[Group], max_tools: int
) -> tuple[list[Group], list[Merge]]:
    """Merge smallest groups until ``len(groups) <= max_tools``."""
    if max_tools < 1:
        raise ValueError("max_tools must be >= 1")

    groups = list(groups)
    merges: list[Merge] = []

    while len(groups) > max_tools:
        # Smallest groups last after this sort; pop the two smallest.
        groups.sort(key=lambda g: (-g.size, g.key))
        smaller = groups.pop()
        larger = groups.pop()
        merged = _merge(larger, smaller)
        merges.append(
            Merge(
                result_key=merged.key,
                source_keys=list(merged.source_tags),
                size=merged.size,
            )
        )
        groups.append(merged)

    groups.sort(key=lambda g: (-g.size, g.key))
    return groups, merges


def _merge(a: Group, b: Group) -> Group:
    source_tags = [*a.source_tags, *b.source_tags]
    key = "_".join(dict.fromkeys(source_tags))[:60]
    return Group(
        key=key,
        title=" & ".join(_titleize(t) for t in source_tags[:3])
        + (" & more" if len(source_tags) > 3 else ""),
        endpoints=[*a.endpoints, *b.endpoints],
        source_tags=source_tags,
    )
