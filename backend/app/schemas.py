from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "Novo chat"


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    pinned: bool | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    pinned: bool = False
    mode: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    pii_redacted: bool = False
    blocked: bool = False
    is_error: bool = False
    attachment_names: list[str] = Field(default_factory=list)
    created_at: datetime


class BlockedResponse(BaseModel):
    blocked: bool = True
    reasons: list[str]
    findings_summary: list[str] = Field(default_factory=list)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DevLoginRequest(BaseModel):
    email: str = "dev@securechat.local"
    display_name: str = "Dev User"
