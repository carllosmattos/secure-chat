from __future__ import annotations

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser
from app.llm.provider import get_llm_provider
from app.models import AuditEvent, ChatSession, Message
from app.services.pipeline import PipelineBlockError, process_message_pipeline
from app.services.quota import QuotaExceededError, check_and_increment_quota
from app.services.vault import rehydrate


async def list_sessions(db: AsyncSession, user: AuthUser) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def create_session(db: AsyncSession, user: AuthUser, title: str = "New chat") -> ChatSession:
    session = ChatSession(user_id=user.id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, user: AuthUser, session_id: uuid.UUID) -> ChatSession | None:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    return result.scalar_one_or_none()


async def list_messages(db: AsyncSession, session_id: uuid.UUID) -> list[Message]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def log_audit(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    *,
    event_type: str,
    prompt_hash: str,
    pii_counts: dict,
    model: str,
    latency_ms: int,
    attachment_count: int,
    decision: str,
    metadata: dict | None = None,
) -> None:
    event = AuditEvent(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        prompt_hash=prompt_hash,
        pii_counts=pii_counts,
        model=model,
        latency_ms=latency_ms,
        attachment_count=attachment_count,
        decision=decision,
        extra_data=metadata or {},
    )
    db.add(event)
    await db.commit()
