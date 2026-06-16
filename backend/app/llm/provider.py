from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

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


class OllamaLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        import json

        import httpx

        payload = {
            "model": model or self._model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content


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
        import json

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


def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaLLMProvider()
    if provider == "bedrock":
        return BedrockLLMProvider()
    return MockLLMProvider()
