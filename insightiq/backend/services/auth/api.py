from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.db import create_engine, create_sessionmaker
from core.models import Tenant, User
from core.security import encode_access_token, hash_password, verify_password
from core.types import Role


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def get_sessionmaker() -> object:
    # Phase 1: keep wiring minimal; Phase 2 will centralize DI.
    settings = get_settings_resolver().resolve()
    engine = create_engine(settings)
    return create_sessionmaker(engine)


async def get_db() -> AsyncSession:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:  # type: ignore[misc]
        yield session


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    tenant = Tenant(name=req.tenant_name)
    user = User(tenant_id=tenant.id, email=req.email, password_hash=hash_password(req.password), role=Role.admin)
    db.add(tenant)
    db.add(user)
    await db.commit()

    settings = get_settings_resolver().resolve()
    token = encode_access_token(settings=settings, user_id=user.id, tenant_id=tenant.id, role=user.role)
    return AuthResponse(access_token=token)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    res = await db.execute(select(User).where(User.email == req.email))
    user = res.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    settings = get_settings_resolver().resolve()
    token = encode_access_token(settings=settings, user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return AuthResponse(access_token=token)

