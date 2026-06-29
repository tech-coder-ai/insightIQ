from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import get_settings_resolver
from core.dev_auth import DEV_TENANT_ID, DEV_USER_ID
from core.security import TokenClaims, decode_access_token
from core.types import Role

bearer = HTTPBearer(auto_error=False)


class RequestContext:
    def __init__(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: Role) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role


def _dev_context() -> RequestContext:
    return RequestContext(user_id=DEV_USER_ID, tenant_id=DEV_TENANT_ID, role=Role.admin)


def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> RequestContext:
    settings = get_settings_resolver().resolve()
    if settings.auth.disabled:
        return _dev_context()
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        claims: TokenClaims = decode_access_token(settings=settings, token=creds.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from None
    return RequestContext(user_id=claims.user_id, tenant_id=claims.tenant_id, role=claims.role)


def require_role(min_role: Role):
    rank = {Role.viewer: 0, Role.editor: 1, Role.admin: 2, Role.super_admin: 3}

    def dep(ctx: RequestContext = Depends(require_auth)) -> RequestContext:
        if rank[ctx.role] < rank[min_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return ctx

    return dep
