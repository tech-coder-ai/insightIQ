from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from config.settings import get_settings_resolver
from core.telemetry.logging import configure_logging
from core.telemetry.otel import setup_otel
from gateway.middleware import CorrelationIdMiddleware, MetricsMiddleware, RateLimitMiddleware
from services.admin.api import router as admin_router
from services.auth.api import router as auth_router
from services.chat.api import router as chat_router
from services.dashboards.api import public_router as dashboards_public_router
from services.dashboards.api import router as dashboards_router
from services.prompt_studio.api import router as prompt_studio_router
from services.talk_to_data.api import router as talk_to_data_router
from services.talk_to_docs.api import router as talk_to_docs_router

settings = get_settings_resolver().resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(json_logs=settings.telemetry.log_json)
    setup_otel(app, settings)
    yield


app = FastAPI(title="InsightIQ Gateway", version="0.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(talk_to_data_router)
app.include_router(talk_to_docs_router)
app.include_router(dashboards_router)
app.include_router(dashboards_public_router)
app.include_router(prompt_studio_router)
app.include_router(admin_router)
