"""Before/after curation report."""

from __future__ import annotations

from dataclasses import dataclass, field

from .budget import Merge


@dataclass
class ToolSummary:
    name: str
    action_count: int
    source_tags: list[str]


@dataclass
class CurationReport:
    raw_count: int
    curated_count: int
    tools: list[ToolSummary] = field(default_factory=list)
    merges: list[Merge] = field(default_factory=list)
    max_tools: int = 0

    @property
    def reduction_pct(self) -> float:
        if self.raw_count == 0:
            return 0.0
        return 100.0 * (1 - self.curated_count / self.raw_count)

    def render(self) -> str:
        lines = [
            "Curation report",
            "===============",
            f"raw tools:     {self.raw_count}",
            f"curated tools: {self.curated_count}  (budget {self.max_tools})",
            f"reduction:     {self.reduction_pct:.0f}%",
            "",
            "Curated tools (actions consolidated):",
        ]
        for tool in sorted(self.tools, key=lambda t: -t.action_count):
            tags = ", ".join(tool.source_tags[:4])
            extra = "" if len(tool.source_tags) <= 4 else f" +{len(tool.source_tags) - 4}"
            lines.append(f"  - {tool.name}: {tool.action_count} actions  [{tags}{extra}]")
        if self.merges:
            lines += ["", "Groups merged to fit the budget:"]
            for merge in self.merges:
                lines.append(
                    f"  - {' + '.join(merge.source_keys)} -> {merge.result_key}"
                )
        return "\n".join(lines)
