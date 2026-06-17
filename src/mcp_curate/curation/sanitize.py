"""Defend against tool-poisoning / prompt-injection in tool descriptions.

A malicious OpenAPI spec can hide instructions aimed at *your* AI agent inside an
operation's description (hidden unicode, fake role tags, "ignore previous
instructions ..."). Those descriptions flow into the tool definitions the model
reads, so the spec becomes a prompt-injection vector against the end user.

Two defenses, both on by default:

* **scrub** — strip invisible/control characters (zero-width, bidi overrides,
  control codes) that have no legitimate place in a description and are the
  classic carrier for hidden instructions. Always safe to remove.
* **scan** — flag descriptions that contain instruction-injection patterns, so
  the user is warned which tools look suspicious (we warn rather than delete, to
  avoid mangling legitimate text).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Patterns that are normal in prose/attacks but rare in legitimate API docs.
_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(the\s+|all\s+)?(previous|prior|above|earlier)\s+"
                r"(instruction|prompt|message|rule)", re.I), "ignore-previous-instructions"),
    (re.compile(r"disregard\s+(the\s+|all\s+)?(previous|prior|above)", re.I),
     "disregard-previous"),
    (re.compile(r"</?\s*(system|assistant|user|tool|instructions?)\s*>", re.I),
     "fake-role-tags"),
    (re.compile(r"\b(new|updated|real)\s+instructions?\s*:", re.I), "new-instructions"),
    (re.compile(r"\bsystem\s+prompt\b", re.I), "mentions-system-prompt"),
    (re.compile(r"do\s+not\s+(tell|inform|reveal|mention|disclose)", re.I),
     "do-not-reveal"),
    (re.compile(r"\bexfiltrat", re.I), "mentions-exfiltration"),
    (re.compile(r"(send|post|upload|leak|exfiltrat\w+)[^\n]{0,40}(\.env|secret|token|"
                r"api[\s_-]?key|credential|password)", re.I), "send-secrets"),
]


@dataclass
class Finding:
    """A tool whose description tripped one or more injection heuristics."""

    tool: str
    reasons: list[str]


def scrub(text: str) -> str:
    """Remove invisible/control characters (zero-width, bidi, control codes)."""
    out = []
    for ch in text:
        if ch in ("\n", "\t"):
            out.append(ch)
            continue
        category = unicodedata.category(ch)
        if category in ("Cc", "Cf"):  # control + format (zero-width, bidi overrides)
            continue
        out.append(ch)
    return "".join(out)


def scan(text: str) -> list[str]:
    """Return labels for any injection patterns found in `text`."""
    return [label for pattern, label in _INJECTION_PATTERNS if pattern.search(text)]


def sanitize_tools(tools: list) -> list[Finding]:
    """Scrub every tool's description in place and flag suspicious ones.

    Returns findings for tools whose (scrubbed) description still matches an
    injection heuristic — surfaced to the user as a warning.
    """
    findings: list[Finding] = []
    for tool in tools:
        tool.description = scrub(tool.description)
        reasons = scan(tool.description)
        if reasons:
            findings.append(Finding(tool=tool.name, reasons=reasons))
    return findings
