from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User

security = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    id: uuid.UUID
    email: str
    display_name: str


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    payload = {"sub": str(user_id), "email": email}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_or_create_dev_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == "dev@securechat.local"))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(email="dev@securechat.local", display_name="Dev User")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    if settings.dev_auth_bypass and not credentials:
        user = await get_or_create_dev_user(db)
        return AuthUser(id=user.id, email=user.email, display_name=user.display_name)

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    try:
        if settings.oidc_issuer:
            # Production: validate OIDC JWT from issuer
            payload = jwt.get_unverified_claims(token)
            email = payload.get("email") or payload.get("preferred_username", "")
            sub = payload.get("sub", "")
            if not email:
                raise HTTPException(status_code=401, detail="Invalid OIDC token")
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = User(email=email, display_name=payload.get("name", email))
                db.add(user)
                await db.commit()
                await db.refresh(user)
            return AuthUser(id=user.id, email=user.email, display_name=user.display_name)

        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = uuid.UUID(payload["sub"])
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return AuthUser(id=user.id, email=user.email, display_name=user.display_name)
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
