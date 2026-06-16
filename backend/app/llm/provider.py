from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Callable

from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...


class MockLLMProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "mock-claude-opus"

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import asyncio

        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        response = (
            "Resposta simulada (modo dev). Recebi sua mensagem redigida com segurança.\n\n"
            f"Contexto (redigido): {last_user[:500]}"
        )
        for word in response.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)


class BedrockLLMProvider(LLMProvider):
    def __init__(self) -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        self._model_id = settings.bedrock_model_id

    @property
    def model_name(self) -> str:
        return self._model_id

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import asyncio

        model_id = model or self._model_id
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }

        loop = asyncio.get_event_loop()

        def _invoke() -> Any:
            return self._client.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )

        response = await loop.run_in_executor(None, _invoke)
        stream = response.get("body")
        if not stream:
            return

        for event in stream:
            chunk = event.get("chunk")
            if not chunk:
                continue
            data = json.loads(chunk["bytes"].decode())
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield text


class OllamaLLMProvider(LLMProvider):
    """Talks to a local (or remote) Ollama server via its native /api/chat endpoint.

    Works with any model pulled into Ollama (llama3, mistral, qwen, phi3, gemma, ...).
    """

    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.llm_request_timeout

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        payload = {
            "model": model or self._model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise RuntimeError(data["error"])
                    text = data.get("message", {}).get("content", "")
                    if text:
                        yield text
                    if data.get("done"):
                        break


class OpenAICompatLLMProvider(LLMProvider):
    """Generic provider for any OpenAI-compatible /chat/completions endpoint.

    Covers the vast majority of hosted and self-hosted LLMs: Groq, OpenRouter,
    Together, Fireworks, DeepSeek, OpenAI, vLLM, LM Studio, llama.cpp server, etc.
    Just point ``OPENAI_BASE_URL`` / ``OPENAI_MODEL`` / ``OPENAI_API_KEY`` at the
    provider you want.
    """

    def __init__(self) -> None:
        self._base_url = settings.openai_base_url.rstrip("/")
        self._model = settings.openai_model
        self._api_key = settings.openai_api_key
        self._timeout = settings.llm_request_timeout

    @property
    def model_name(self) -> str:
        return self._model

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": model or self._model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:") :].strip()
                    if chunk == "[DONE]":
                        break
                    data = json.loads(chunk)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    text = choices[0].get("delta", {}).get("content", "")
                    if text:
                        yield text


class AutoLLMProvider(LLMProvider):
    """Meta-provider that switches between several backends automatically.

    Strategies (``LLM_AUTO_STRATEGY``):
      - ``failover``    : always try candidates in order, fall through on error
      - ``round_robin`` : rotate the starting candidate each request (load balance)
      - ``random``      : pick a random starting candidate each request

    In every strategy, if a backend errors **before emitting any token**, the next
    candidate is tried — so a dead/unconfigured provider never breaks a request.
    """

    def __init__(self) -> None:
        self._strategy = settings.llm_auto_strategy.lower()
        names = [n.strip() for n in settings.llm_auto_providers.split(",") if n.strip()]
        self._candidates: list[tuple[str, LLMProvider]] = []
        for name in names:
            if name in ("auto", ""):
                continue
            factory = PROVIDER_REGISTRY.get(name)
            if factory is None:
                continue
            try:
                self._candidates.append((name, factory()))
            except Exception:
                # Provider not installed/configured (e.g. Bedrock without creds) — skip it.
                continue
        if not self._candidates:
            self._candidates.append(("mock", MockLLMProvider()))
        self._rr_index = 0
        self._last_used = self._candidates[0][1].model_name

    @property
    def model_name(self) -> str:
        return f"auto:{self._last_used}"

    def _ordered_candidates(self) -> list[tuple[str, LLMProvider]]:
        n = len(self._candidates)
        if self._strategy == "random":
            order = list(range(n))
            random.shuffle(order)
        elif self._strategy == "round_robin":
            start = self._rr_index % n
            self._rr_index = (self._rr_index + 1) % n
            order = [(start + i) % n for i in range(n)]
        else:  # failover
            order = list(range(n))
        return [self._candidates[i] for i in order]

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        last_exc: Exception | None = None
        for _name, provider in self._ordered_candidates():
            produced = False
            try:
                async for chunk in provider.stream_completion(messages, model=model):
                    if not produced:
                        produced = True
                        self._last_used = provider.model_name
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 - resilience across backends
                last_exc = exc
                if produced:
                    # Already streamed partial output; can't cleanly switch backends.
                    raise
                continue
        if last_exc is not None:
            raise last_exc


# Pluggable registry — add any new LLM backend with a single entry here.
PROVIDER_REGISTRY: dict[str, Callable[[], LLMProvider]] = {
    "mock": MockLLMProvider,
    "bedrock": BedrockLLMProvider,
    "ollama": OllamaLLMProvider,
    "openai": OpenAICompatLLMProvider,
    "auto": AutoLLMProvider,
}


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """Return a provider instance. ``name`` overrides ``LLM_PROVIDER`` for one request."""
    provider = (name or settings.llm_provider).lower()
    factory = PROVIDER_REGISTRY.get(provider, MockLLMProvider)
    return factory()


def provider_catalog() -> list[dict[str, Any]]:
    """Front-end friendly list of selectable backends and their default models."""
    return [
        {"id": "auto", "label": "Auto (balanceado + failover)", "default_model": None},
        {"id": "ollama", "label": "Ollama (local)", "default_model": settings.ollama_model},
        {"id": "openai", "label": "OpenAI-compatível", "default_model": settings.openai_model},
        {"id": "bedrock", "label": "AWS Bedrock (Claude)", "default_model": settings.bedrock_model_id},
        {"id": "mock", "label": "Mock (dev)", "default_model": "mock-claude-opus"},
    ]
