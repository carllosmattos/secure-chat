from __future__ import annotations

import random
from typing import Any

from app.config import Settings

_rr_index = 0


def _settings() -> Settings:
    """Read current ``.env`` on each call (avoids stale in-memory config)."""
    return Settings()


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def configured_models() -> list[str]:
    """Models from ``LLM_MODELS``, ensuring ``OPENAI_MODEL`` is included."""
    cfg = _settings()
    models = _parse_csv(cfg.llm_models)
    default = cfg.openai_model.strip()
    if default and default not in models:
        models.insert(0, default)
    if not models and default:
        return [default]
    return models


def uses_model_pool(provider: str | None) -> bool:
    """Model list / balancing applies to the OpenAI-compatible backend."""
    cfg = _settings()
    effective = (provider or cfg.llm_provider).lower()
    return effective == "openai"


def ordered_models(provider: str | None, override: str | None) -> list[str]:
    """Resolve model candidates for a request (manual pick or balanced list)."""
    if override:
        return [override]

    cfg = _settings()
    if not uses_model_pool(provider):
        return []

    models = configured_models()
    if not models:
        return [cfg.openai_model]

    strategy = cfg.llm_model_strategy.lower()
    if strategy == "manual":
        return [cfg.openai_model]

    n = len(models)
    if strategy == "random":
        order = list(range(n))
        random.shuffle(order)
    elif strategy == "round_robin":
        global _rr_index
        start = _rr_index % n
        _rr_index = (_rr_index + 1) % n
        order = [(start + i) % n for i in range(n)]
    else:  # failover
        order = list(range(n))

    return [models[i] for i in order]


def model_catalog() -> dict[str, Any]:
    cfg = _settings()
    return {
        "default_model": cfg.openai_model,
        "models": configured_models(),
        "strategy": cfg.llm_model_strategy,
    }
