from __future__ import annotations

import json


def format_http_error(status_code: int, body: bytes, *, model: str) -> str:
    """Turn an OpenAI-compat error response into a short user-facing message."""
    text = body.decode("utf-8", errors="replace").strip()
    if text:
        try:
            data = json.loads(text)
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                msg = str(err["message"])
                return f"[{model}] {msg}"
            if isinstance(err, str):
                return f"[{model}] {err}"
        except json.JSONDecodeError:
            pass
        if len(text) > 300:
            text = text[:300] + "..."
        return f"[{model}] HTTP {status_code}: {text}"
    return f"[{model}] HTTP {status_code}"


def is_openrouter_base_url(base_url: str) -> bool:
    return "openrouter.ai" in base_url.lower()
