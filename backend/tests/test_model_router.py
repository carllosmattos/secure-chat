from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


def _reload_model_router():
    import app.llm.model_router as model_router

    importlib.reload(model_router)
    return model_router


@pytest.fixture
def model_router():
    with patch("app.llm.model_router.settings") as mock_settings:
        mock_settings.openai_model = "default-model"
        mock_settings.llm_models = "model-a,model-b,model-c"
        mock_settings.llm_model_strategy = "failover"
        mock_settings.llm_provider = "openai"
        yield _reload_model_router()


def test_configured_models_includes_default(model_router):
    models = model_router.configured_models()
    assert models[0] == "default-model"
    assert models == ["default-model", "model-a", "model-b", "model-c"]


def test_ordered_models_manual_uses_default(model_router):
    model_router.settings.llm_model_strategy = "manual"
    assert model_router.ordered_models("openai", None) == ["default-model"]


def test_ordered_models_override_wins(model_router):
    assert model_router.ordered_models("openai", "picked-model") == ["picked-model"]


def test_ordered_models_round_robin_rotates(model_router):
    model_router.settings.llm_model_strategy = "round_robin"
    first = model_router.ordered_models("openai", None)[0]
    second = model_router.ordered_models("openai", None)[0]
    assert first != second


def test_ordered_models_skipped_for_ollama(model_router):
    assert model_router.ordered_models("ollama", None) == []


def test_model_catalog_shape(model_router):
    catalog = model_router.model_catalog()
    assert catalog["default_model"] == "default-model"
    assert len(catalog["models"]) == 4
    assert catalog["strategy"] == "failover"
