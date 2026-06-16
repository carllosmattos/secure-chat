"""Policy application for detection findings."""

from __future__ import annotations

from dataclasses import dataclass, field

from security_patterns.detector import Finding
from security_patterns.patterns import Profile


@dataclass
class PolicyResult:
    block: bool
    reasons: list[str] = field(default_factory=list)
    redact_kinds: set[str] = field(default_factory=set)


def apply_policy(findings: list[Finding], profile: Profile = "pii-redact") -> PolicyResult:
    """Apply block/redact policy based on profile."""
    result = PolicyResult(block=False)

    for finding in findings:
        if profile == "strict":
            result.block = True
            result.reasons.append(f"{finding.label} detected (strict profile)")
            continue

        if finding.severity == "block":
            result.block = True
            result.reasons.append(f"{finding.label} detected — send blocked")
        elif finding.severity == "redact":
            result.redact_kinds.add(finding.kind)

    return result
