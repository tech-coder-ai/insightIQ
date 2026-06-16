from __future__ import annotations

import datetime as dt
import uuid

import bcrypt
from jose import jwt

from config.settings import AppSettings
from core.types import Role


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def encode_access_token(
    *,
    settings: AppSettings,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: Role,
) -> str:
    if not settings.jwt.private_key_pem:
        raise ValueError("INSIGHTIQ_JWT__PRIVATE_KEY_PEM is required for RS256")
    now = dt.datetime.now(dt.UTC)
    payload = {
        "iss": settings.jwt.issuer,
        "aud": settings.jwt.audience,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=settings.jwt.access_token_ttl_seconds)).timestamp()),
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role.value,
    }
    return jwt.encode(payload, settings.jwt.private_key_pem, algorithm="RS256")


class TokenClaims:
    def __init__(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: Role) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role


def decode_access_token(*, settings: AppSettings, token: str) -> TokenClaims:
    if not settings.jwt.public_key_pem:
        raise ValueError("INSIGHTIQ_JWT__PUBLIC_KEY_PEM is required for RS256")
    payload = jwt.decode(
        token,
        settings.jwt.public_key_pem,
        algorithms=["RS256"],
        audience=settings.jwt.audience,
        issuer=settings.jwt.issuer,
    )
    return TokenClaims(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tid"]),
        role=Role(payload["role"]),
    )
