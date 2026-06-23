from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.provider import LLMProvider


async def stream_with_model_failover(
    llm: LLMProvider,
    messages: list[dict[str, str]],
    models: list[str],
) -> AsyncIterator[tuple[str, str]]:
    """Stream completion, trying each model until one succeeds.

    Yields ``(chunk, model_id)``. If a model errors before the first token,
    the next candidate is tried. Partial output from a failed model is re-raised.
    """
    if not models:
        async for chunk in llm.stream_completion(messages):
            yield chunk, llm.model_name
        return

    last_exc: Exception | None = None
    failures: list[str] = []
    for candidate in models:
        produced = False
        try:
            async for chunk in llm.stream_completion(messages, model=candidate):
                if not produced:
                    produced = True
                yield chunk, candidate
            return
        except Exception as exc:  # noqa: BLE001 — failover across models
            last_exc = exc
            failures.append(str(exc))
            if produced:
                raise
            continue

    if last_exc is not None:
        if len(failures) > 1:
            raise RuntimeError(
                "Todos os modelos falharam:\n" + "\n".join(failures)
            ) from last_exc
        raise last_exc
