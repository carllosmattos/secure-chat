"""Reversible PII redaction with numbered placeholders."""

from __future__ import annotations

from security_patterns.detector import Finding, detect
from security_patterns.patterns import Profile, REDACT_PATTERNS
from security_patterns.policy import apply_policy


def _kind_prefix(kind: str) -> str:
    return kind.upper().replace("_", "")


def redact_text(
    text: str,
    profile: Profile = "pii-redact",
) -> tuple[str, dict[str, str]]:
    """
    Redact PII in text, returning (redacted_text, mapping).
    mapping: placeholder -> original value (for ephemeral vault).
    """
    findings = detect(text)
    policy = apply_policy(findings, profile)

    if policy.block:
        return text, {}

    redact_findings = [f for f in findings if f.severity == "redact"]
    if not redact_findings:
        return text, {}

    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    parts: list[str] = []
    last = 0

    for finding in redact_findings:
        parts.append(text[last : finding.start])
        prefix = _kind_prefix(finding.kind)
        counters[prefix] = counters.get(prefix, 0) + 1
        placeholder = f"[{prefix}_{counters[prefix]}]"
        mapping[placeholder] = finding.matched
        parts.append(placeholder)
        last = finding.end

    parts.append(text[last:])
    return "".join(parts), mapping
