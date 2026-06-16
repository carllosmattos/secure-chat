"""Sensitive file extension and filename guards."""

from __future__ import annotations

import os

from security_patterns.patterns import SENSITIVE_EXTENSIONS, SENSITIVE_FILENAMES


def is_sensitive_filename(filename: str) -> bool:
    base = os.path.basename(filename).lower()
    if base in SENSITIVE_FILENAMES:
        return True
    _, ext = os.path.splitext(base)
    return ext in SENSITIVE_EXTENSIONS


def block_reason_for_filename(filename: str) -> str | None:
    if not is_sensitive_filename(filename):
        return None
    return f"Sensitive file type blocked: {os.path.basename(filename)}"
