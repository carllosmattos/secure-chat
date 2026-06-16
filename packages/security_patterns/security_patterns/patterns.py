"""Regex patterns ported from cursor-security patterns.js."""

import re
from dataclasses import dataclass
from typing import Literal

Severity = Literal["block", "redact"]
Kind = Literal[
    "aws_access_key",
    "aws_secret_key",
    "jwt",
    "bearer_token",
    "api_key",
    "private_key_pem",
    "jdbc",
    "cpf",
    "cnpj",
    "email",
    "phone",
    "date",
    "name",
    "iban",
    "credit_card",
    "routing_number",
]


@dataclass(frozen=True)
class PatternDef:
    kind: Kind
    label: str
    severity: Severity
    regex: re.Pattern[str]


def _compile(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


BLOCK_PATTERNS: list[PatternDef] = [
    PatternDef(
        "aws_access_key",
        "AWS Access Key",
        "block",
        _compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    ),
    PatternDef(
        "aws_secret_key",
        "AWS Secret Key",
        "block",
        _compile(r"(?i)(aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"),
    ),
    PatternDef(
        "jwt",
        "JWT Token",
        "block",
        _compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    PatternDef(
        "bearer_token",
        "Bearer Token",
        "block",
        _compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b"),
    ),
    PatternDef(
        "api_key",
        "API Key",
        "block",
        _compile(
            r"(?i)(api[_-]?key|apikey|x-api-key)\s*[=:]\s*['\"]?([A-Za-z0-9\-._~+/]{16,})['\"]?"
        ),
    ),
    PatternDef(
        "private_key_pem",
        "Private Key (PEM)",
        "block",
        _compile(
            r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
            re.MULTILINE,
        ),
    ),
    PatternDef(
        "jdbc",
        "JDBC Connection String",
        "block",
        _compile(
            r"jdbc:[a-zA-Z0-9]+://[^\s\"']+",
            re.IGNORECASE,
        ),
    ),
]

REDACT_PATTERNS: list[PatternDef] = [
    PatternDef(
        "cpf",
        "CPF",
        "redact",
        _compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    ),
    PatternDef(
        "cnpj",
        "CNPJ",
        "redact",
        _compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    ),
    PatternDef(
        "email",
        "Email",
        "redact",
        _compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    PatternDef(
        "phone",
        "Phone",
        "redact",
        _compile(
            r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?\d{4,5}[-.\s]?\d{4}\b"
        ),
    ),
    PatternDef(
        "date",
        "Date",
        "redact",
        _compile(
            r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2})\b"
        ),
    ),
    PatternDef(
        "name",
        "Name",
        "redact",
        _compile(r"\b[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ][a-záàâãéèêíïóôõöúçñ]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ][a-záàâãéèêíïóôõöúçñ]+)+\b"),
    ),
    PatternDef(
        "iban",
        "IBAN",
        "redact",
        _compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    ),
    PatternDef(
        "credit_card",
        "Credit Card",
        "redact",
        _compile(r"\b(?:\d[ -]*?){13,19}\b"),
    ),
    PatternDef(
        "routing_number",
        "Routing Number",
        "redact",
        _compile(r"\b\d{9}\b"),
    ),
]

ALL_PATTERNS: list[PatternDef] = BLOCK_PATTERNS + REDACT_PATTERNS

Profile = Literal["strict", "pii-redact"]

SENSITIVE_EXTENSIONS = frozenset(
    {
        ".key",
        ".crt",
        ".pem",
        ".p12",
        ".pfx",
        ".jks",
        ".keystore",
    }
)

SENSITIVE_FILENAMES = frozenset({"id_rsa", "id_rsa.pub"})
