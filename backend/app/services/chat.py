from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser
from app.models import AuditEvent, ChatSession, Message

DEFAULT_TITLES = frozenset({"New chat", "Novo chat", ""})
AUTO_TITLE_MAX_LEN = 60


def derive_session_title(text: str) -> str:
    line = text.strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    if not line:
        return "Novo chat"
    if len(line) <= AUTO_TITLE_MAX_LEN:
        return line
    return line[:AUTO_TITLE_MAX_LEN].rstrip() + "…"


async def list_sessions(db: AsyncSession, user: AuthUser) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def create_session(db: AsyncSession, user: AuthUser, title: str = "Novo chat") -> ChatSession:
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


async def update_session(
    db: AsyncSession,
    user: AuthUser,
    session_id: uuid.UUID,
    *,
    title: str | None = None,
    pinned: bool | None = None,
) -> ChatSession | None:
    session = await get_session(db, user, session_id)
    if not session:
        return None
    if title is not None:
        session.title = title
    if pinned is not None:
        session.pinned = pinned
    session.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(db: AsyncSession, user: AuthUser, session_id: uuid.UUID) -> bool:
    session = await get_session(db, user, session_id)
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True


async def touch_session(db: AsyncSession, session: ChatSession) -> None:
    session.updated_at = datetime.now(UTC)
    await db.commit()


async def maybe_auto_title(
    db: AsyncSession,
    session: ChatSession,
    user_text: str,
    message_count: int,
) -> str | None:
    if message_count != 1 or session.title not in DEFAULT_TITLES:
        return None
    session.title = derive_session_title(user_text)
    session.updated_at = datetime.now(UTC)
    await db.commit()
    return session.title


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
