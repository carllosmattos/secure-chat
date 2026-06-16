from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import QuotaUsage


class QuotaExceededError(Exception):
    pass


async def check_and_increment_quota(db: AsyncSession, user_id: uuid.UUID) -> None:
    today = date.today().isoformat()
    result = await db.execute(
        select(QuotaUsage).where(QuotaUsage.user_id == user_id, QuotaUsage.day == today)
    )
    usage = result.scalar_one_or_none()
    if usage and usage.message_count >= settings.daily_message_quota:
        raise QuotaExceededError(f"Daily quota of {settings.daily_message_quota} messages exceeded")
    if not usage:
        usage = QuotaUsage(user_id=user_id, day=today, message_count=0)
        db.add(usage)
    usage.message_count += 1
    await db.commit()
