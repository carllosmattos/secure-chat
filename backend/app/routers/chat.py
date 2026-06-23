from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthUser, create_access_token, get_current_user
from app.database import get_db
from app.llm.model_router import model_catalog, ordered_models
from app.llm.provider import get_llm_provider, provider_catalog
from app.llm.streaming import stream_with_model_failover
from app.models import Message, User
from app.schemas import (
    AuthTokenResponse,
    BlockedResponse,
    DevLoginRequest,
    MessageOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)
from app.services import chat as chat_service
from app.services.pipeline import PipelineBlockError, process_message_pipeline
from app.services.quota import QuotaExceededError, check_and_increment_quota
from app.services.vault import rehydrate, vault

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/auth/dev-login", response_model=AuthTokenResponse)
async def dev_login(body: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=body.email, display_name=body.display_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    token = create_access_token(user.id, user.email)
    return AuthTokenResponse(access_token=token)


@router.get("/llm/providers")
async def list_llm_providers():
    from app.config import settings

    return {
        "active": settings.llm_provider,
        "auto_strategy": settings.llm_auto_strategy,
        "auto_providers": [p.strip() for p in settings.llm_auto_providers.split(",") if p.strip()],
        "providers": provider_catalog(),
        **model_catalog(),
    }


@router.get("/sessions", response_model=list[SessionOut])
async def get_sessions(user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await chat_service.list_sessions(db, user)


@router.post("/sessions", response_model=SessionOut)
async def create_session(
    body: SessionCreate,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.create_session(db, user, body.title)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.update_session(
        db,
        user,
        session_id,
        title=body.title,
        pinned=body.pinned,
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await chat_service.delete_session(db, user, session_id)
    if not deleted:
        raise HTTPException(404, "Session not found")
    vault.clear(session_id)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(
    session_id: uuid.UUID,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, user, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    messages = await chat_service.list_messages(db, session_id)
    mapping = vault.get_all(session_id)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=rehydrate(m.content_redacted, mapping),
            pii_redacted=m.pii_redacted,
            blocked=m.blocked,
            is_error=m.is_error,
            attachment_names=m.attachment_names or [],
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, user, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    try:
        await check_and_increment_quota(db, user.id)
    except QuotaExceededError as exc:
        raise HTTPException(429, str(exc)) from exc

    file_tuples: list[tuple[str, bytes]] = []
    for f in files:
        if f.filename:
            file_tuples.append((f.filename, await f.read()))

    start = time.perf_counter()
    try:
        pipeline = await process_message_pipeline(session_id, content, file_tuples)
    except PipelineBlockError as exc:
        await chat_service.log_audit(
            db,
            user.id,
            session_id,
            event_type="message_blocked",
            prompt_hash="",
            pii_counts={},
            model="",
            latency_ms=int((time.perf_counter() - start) * 1000),
            attachment_count=len(file_tuples),
            decision="block",
            metadata={"reasons": exc.reasons},
        )
        blocked_msg = Message(
            session_id=session_id,
            role="user",
            content_redacted="[BLOCKED ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â sensitive content detected]",
            blocked=True,
            attachment_names=[n for n, _ in file_tuples],
        )
        db.add(blocked_msg)
        await db.commit()
        return BlockedResponse(reasons=exc.reasons, findings_summary=exc.findings_summary)

    user_msg = Message(
        session_id=session_id,
        role="user",
        content_redacted=pipeline.redacted_text,
        pii_redacted=pipeline.pii_redacted,
        attachment_names=pipeline.attachment_names,
    )
    db.add(user_msg)
    await db.commit()

    history = await chat_service.list_messages(db, session_id)
    user_message_count = sum(1 for m in history if m.role == "user")
    new_title = await chat_service.maybe_auto_title(
        db, session, pipeline.redacted_text, user_message_count
    )
    await chat_service.touch_session(db, session)

    llm = get_llm_provider(provider)
    llm_messages = [{"role": m.role, "content": m.content_redacted} for m in history]
    llm_messages.append({"role": "user", "content": pipeline.redacted_text})

    model_candidates = ordered_models(provider, model)

    async def event_generator():
        full_response = ""
        used_model = llm.model_name
        try:
            async for chunk, resolved_model in stream_with_model_failover(
                llm, llm_messages, model_candidates
            ):
                used_model = resolved_model
                full_response += chunk
                yield {"event": "token", "data": json.dumps({"text": chunk})}
        except Exception as exc:
            assistant_msg = Message(
                session_id=session_id,
                role="assistant",
                content_redacted=full_response,
                is_error=True,
            )
            db.add(assistant_msg)
            await db.commit()

            latency = int((time.perf_counter() - start) * 1000)
            await chat_service.log_audit(
                db,
                user.id,
                session_id,
                event_type="message_failed",
                prompt_hash=pipeline.prompt_hash,
                pii_counts=pipeline.pii_counts,
                model=used_model,
                latency_ms=latency,
                attachment_count=len(file_tuples),
                decision="error",
                metadata={"error": str(exc)},
            )

            done_payload: dict = {
                "message_id": str(assistant_msg.id),
                "is_error": True,
            }
            if new_title:
                done_payload["title"] = new_title
            yield {"event": "done", "data": json.dumps(done_payload)}
            return

        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content_redacted=full_response,
        )
        db.add(assistant_msg)
        await db.commit()

        mapping = vault.get_all(session_id)
        rehydrated = rehydrate(full_response, mapping)

        latency = int((time.perf_counter() - start) * 1000)
        await chat_service.log_audit(
            db,
            user.id,
            session_id,
            event_type="message_sent",
            prompt_hash=pipeline.prompt_hash,
            pii_counts=pipeline.pii_counts,
            model=used_model,
            latency_ms=latency,
            attachment_count=len(file_tuples),
            decision="redact" if pipeline.pii_redacted else "allow",
        )

        done_payload = {
            "message_id": str(assistant_msg.id),
            "content": rehydrated,
            "pii_redacted": pipeline.pii_redacted,
            "model": used_model,
        }
        if new_title:
            done_payload["title"] = new_title

        yield {
            "event": "done",
            "data": json.dumps(done_payload),
        }

    return EventSourceResponse(event_generator())
