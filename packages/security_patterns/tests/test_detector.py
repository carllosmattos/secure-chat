"""Tests for security_patterns."""

import pytest

from security_patterns import apply_policy, detect, redact_text


def test_detect_aws_key():
    findings = detect("key is AKIAIOSFODNN7EXAMPLE here")
    assert any(f.kind == "aws_access_key" for f in findings)


def test_detect_jwt():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    findings = detect(f"token {token}")
    assert any(f.kind == "jwt" for f in findings)


def test_redact_cpf():
    text = "CPF do cliente: 111.444.777-35"
    redacted, mapping = redact_text(text)
    assert "111.444.777-35" not in redacted
    assert "[CPF_1]" in redacted
    assert mapping["[CPF_1]"] == "111.444.777-35"


def test_block_bearer():
    findings = detect("Authorization: Bearer abcdefghijklmnopqrstuvwxyz")
    policy = apply_policy(findings)
    assert policy.block is True


def test_strict_profile_blocks_pii():
    text = "email test@example.com"
    findings = detect(text)
    policy = apply_policy(findings, "strict")
    assert policy.block is True
