"""The curation pipeline: group -> budget -> describe -> build meta-tools."""

from __future__ import annotations

from dataclasses import dataclass

from ..parser.model import Spec
from ..server.builder import Tool, build_meta_tool, build_raw_tools, meta_actions
from .budget import enforce_budget
from .describer import Describer, DeterministicDescriber, render_description
from .grouper import group_endpoints, split_to_budget
from .report import CurationReport, ToolSummary
from .sanitize import sanitize_tools

DEFAULT_MAX_TOOLS = 40
DEFAULT_MAX_ACTIONS = 30


@dataclass
class CurationResult:
    raw_tools: list[Tool]
    curated_tools: list[Tool]
    report: CurationReport


def curate(
    spec: Spec,
    max_tools: int = DEFAULT_MAX_TOOLS,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    describer: Describer | None = None,
) -> CurationResult:
    """Consolidate a spec's endpoints into a curated, budget-bounded tool set.

    Pipeline: group by tag -> merge smallest related groups to fit the tool
    budget -> split oversized groups into focused sub-tools using whatever
    headroom is left under ``max_tools`` -> describe and build meta-tools.

    Merging first (not splitting first) means a tight budget keeps tools clean
    instead of forcing unrelated tags together; splitting then only happens when
    there is room for it.
    """
    describer = describer or DeterministicDescriber()
    raw_tools = build_raw_tools(spec)

    groups = group_endpoints(spec)
    groups, merges = enforce_budget(groups, max_tools)
    groups = split_to_budget(groups, max_actions, max_tools)

    curated: list[Tool] = []
    summaries: list[ToolSummary] = []
    used_names: set[str] = set()
    for group in groups:
        actions = meta_actions(group.endpoints, group.source_tags)
        name, lead = describer.describe(group, actions)
        name = _unique(name, used_names)
        description = render_description(lead, actions)
        curated.append(build_meta_tool(name, description, actions))
        summaries.append(
            ToolSummary(
                name=name,
                action_count=len(actions),
                source_tags=list(group.source_tags),
            )
        )

    # Scrub hidden characters from descriptions and flag injection attempts.
    findings = sanitize_tools(curated)

    report = CurationReport(
        raw_count=len(raw_tools),
        curated_count=len(curated),
        tools=summaries,
        merges=merges,
        max_tools=max_tools,
        security_findings=findings,
    )
    return CurationResult(raw_tools=raw_tools, curated_tools=curated, report=report)


def _unique(name: str, used: set[str]) -> str:
    candidate = name
    i = 2
    while candidate in used:
        candidate = f"{name}_{i}"
        i += 1
    used.add(candidate)
    return candidate
