from __future__ import annotations

import base64
import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class EphemeralVault(ABC):
    @abstractmethod
    def store(self, session_id: uuid.UUID, mapping: dict[str, str]) -> None:
        ...

    @abstractmethod
    def get_all(self, session_id: uuid.UUID) -> dict[str, str]:
        ...

    @abstractmethod
    def clear(self, session_id: uuid.UUID) -> None:
        ...


class InMemoryVault(EphemeralVault):
    """MVP: encrypted in-memory store with TTL tracking."""

    def __init__(self, encryption_key: str, ttl_seconds: int) -> None:
        self._fernet = Fernet(_derive_fernet_key(encryption_key))
        self._ttl = ttl_seconds
        self._store: dict[str, bytes] = {}

    def _key(self, session_id: uuid.UUID) -> str:
        return str(session_id)

    def store(self, session_id: uuid.UUID, mapping: dict[str, str]) -> None:
        if not mapping:
            return
        existing = self.get_all(session_id)
        existing.update(mapping)
        payload = json.dumps(existing).encode()
        self._store[self._key(session_id)] = self._fernet.encrypt(payload)

    def get_all(self, session_id: uuid.UUID) -> dict[str, str]:
        encrypted = self._store.get(self._key(session_id))
        if not encrypted:
            return {}
        try:
            data = self._fernet.decrypt(encrypted)
            return json.loads(data)
        except (InvalidToken, json.JSONDecodeError):
            return {}

    def clear(self, session_id: uuid.UUID) -> None:
        self._store.pop(self._key(session_id), None)


def rehydrate(text: str, mapping: dict[str, str]) -> str:
    """Replace placeholders with original values for user display."""
    result = text
    for placeholder, value in sorted(mapping.items(), key=lambda x: -len(x[0])):
        result = result.replace(placeholder, value)
    return result


def merge_mappings(*mappings: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for m in mappings:
        merged.update(m)
    return merged


vault: EphemeralVault = InMemoryVault(settings.vault_encryption_key, settings.vault_ttl_seconds)
