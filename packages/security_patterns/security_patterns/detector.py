"""Deterministic secret/PII detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

from security_patterns.patterns import ALL_PATTERNS, Kind, PatternDef, Severity
from security_patterns.validators import is_valid_cpf, is_valid_credit_card, is_valid_luhn_candidate


@dataclass(frozen=True)
class Finding:
    kind: Kind
    label: str
    severity: Severity
    start: int
    end: int
    matched: str


def _validate_finding(pattern: PatternDef, matched: str) -> bool:
    if pattern.kind == "cpf":
        return is_valid_cpf(matched)
    if pattern.kind == "credit_card":
        return is_valid_credit_card(matched)
    if pattern.kind == "routing_number":
        digits = "".join(c for c in matched if c.isdigit())
        return len(digits) == 9
    if pattern.kind == "aws_secret_key":
        return True
    if pattern.kind == "api_key":
        return True
    return True


def _extract_match(pattern: PatternDef, match: re.Match[str]) -> str:
    if pattern.kind in ("aws_secret_key", "api_key") and match.lastindex and match.lastindex >= 2:
        return match.group(2)
    return match.group(0)


def detect(text: str) -> list[Finding]:
    """Scan text for secrets and PII. Returns non-overlapping findings (block first)."""
    raw: list[Finding] = []

    for pattern in ALL_PATTERNS:
        for match in pattern.regex.finditer(text):
            matched = _extract_match(pattern, match)
            if not _validate_finding(pattern, matched):
                continue
            raw.append(
                Finding(
                    kind=pattern.kind,
                    label=pattern.label,
                    severity=pattern.severity,
                    start=match.start(),
                    end=match.end(),
                    matched=matched,
                )
            )

    raw.sort(key=lambda f: (f.start, -(f.end - f.start), f.severity == "block"), reverse=False)
    # Prefer block findings and longer spans; remove overlaps
    raw.sort(key=lambda f: (-(f.end - f.start), f.severity != "block", f.start))

    selected: list[Finding] = []
    occupied: list[tuple[int, int]] = []

    for finding in raw:
        overlap = any(not (finding.end <= s or finding.start >= e) for s, e in occupied)
        if overlap:
            continue
        selected.append(finding)
        occupied.append((finding.start, finding.end))

    selected.sort(key=lambda f: f.start)
    return selected
