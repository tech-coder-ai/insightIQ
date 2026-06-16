from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings_resolver
from services.auth.api import router as auth_router
from services.chat.api import router as chat_router


app = FastAPI(title="InsightIQ Gateway", version="0.0.0")
settings = get_settings_resolver().resolve()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(chat_router)

