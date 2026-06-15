"""Eval report: the headline raw-vs-curated comparison plus a per-case table."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaseResult:
    request: str
    operation_id: str
    expected_raw: str
    raw_pick: str | None
    raw_correct: bool
    expected_curated: str
    expected_action: str
    curated_pick: str | None
    curated_action: str | None
    curated_correct: bool
    curated_action_correct: bool
    # Argument-construction scoring (None when the case declares no expected args).
    has_expected_args: bool = False
    raw_arg_correct: bool | None = None
    curated_arg_correct: bool | None = None


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    raw_tool_count: int = 0
    curated_tool_count: int = 0

    @property
    def total(self) -> int:
        return len(self.results)

    def _pct(self, n: int) -> float:
        return 100.0 * n / self.total if self.total else 0.0

    @property
    def raw_accuracy(self) -> float:
        return self._pct(sum(r.raw_correct for r in self.results))

    @property
    def curated_accuracy(self) -> float:
        return self._pct(sum(r.curated_correct for r in self.results))

    @property
    def curated_action_accuracy(self) -> float:
        return self._pct(sum(r.curated_action_correct for r in self.results))

    @property
    def _arg_cases(self) -> list[CaseResult]:
        return [r for r in self.results if r.has_expected_args]

    def _arg_pct(self, attr: str) -> float:
        cases = self._arg_cases
        if not cases:
            return 0.0
        return 100.0 * sum(bool(getattr(r, attr)) for r in cases) / len(cases)

    @property
    def raw_arg_accuracy(self) -> float:
        return self._arg_pct("raw_arg_correct")

    @property
    def curated_arg_accuracy(self) -> float:
        return self._arg_pct("curated_arg_correct")

    def render(self) -> str:
        lines = [
            "Eval: raw vs curated tool selection",
            "===================================",
            f"cases: {self.total}   raw tools: {self.raw_tool_count}   "
            f"curated tools: {self.curated_tool_count}",
            "",
            f"raw     correct-tool selection: {self.raw_accuracy:5.0f}%",
            f"curated correct-tool selection: {self.curated_accuracy:5.0f}%",
            f"  -> improvement: {self.curated_accuracy - self.raw_accuracy:+.0f} points",
            f"curated tool+action correct:    {self.curated_action_accuracy:5.0f}%",
        ]
        if self._arg_cases:
            lines += [
                "",
                f"argument construction ({len(self._arg_cases)} cases with expected args):",
                f"  raw     correct args: {self.raw_arg_accuracy:5.0f}%",
                f"  curated correct args: {self.curated_arg_accuracy:5.0f}%",
            ]
        lines += [
            "",
            "Per-case (request -> raw pick | curated pick.action):",
        ]
        for r in self.results:
            raw_mark = "✓" if r.raw_correct else "✗"
            cur_mark = "✓" if r.curated_correct else "✗"
            lines.append(
                f"  {raw_mark}{cur_mark} {r.request[:48]!r}\n"
                f"        raw: {r.raw_pick} (want {r.expected_raw})\n"
                f"        cur: {r.curated_pick}.{r.curated_action} "
                f"(want {r.expected_curated}.{r.expected_action})"
            )
        if self.skipped:
            lines += ["", f"skipped {len(self.skipped)} case(s) (operationId not found): "
                      + ", ".join(self.skipped)]
        return "\n".join(lines)
