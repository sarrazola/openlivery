import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import new_session
from .services.conversation_state import resolve_idle_ai_conversations
from .routers import (
    agency,
    agent_tools,
    agents,
    auth,
    catalog,
    clients,
    conversations,
    dashboard,
    domains,
    industries,
    mobile,
    portal,
    providers,
    whatsapp,
    whatsapp_cloud,
    whatsapp_cloud_webhook,
    widget,
    webchat,
)


settings = get_settings()
logger = logging.getLogger(__name__)

AUTO_RESOLVE_SWEEP_SECONDS = 15 * 60


async def _auto_resolve_loop() -> None:
    """Close idle AI conversations on a timer, for as long as the app runs."""
    while True:
        await asyncio.sleep(AUTO_RESOLVE_SWEEP_SECONDS)
        try:
            with new_session() as db:
                closed = resolve_idle_ai_conversations(db, hours=get_settings().auto_resolve_after_hours)
            if closed:
                logger.info("Auto-resolved %d idle AI conversation(s)", closed)
        except Exception:  # noqa: BLE001 - a failed sweep must not stop the next one
            logger.exception("Auto-resolve sweep failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    sweeper = asyncio.create_task(_auto_resolve_loop()) if settings.auto_resolve_after_hours > 0 else None
    try:
        yield
    finally:
        if sweeper:
            sweeper.cancel()


app = FastAPI(
    title="OpenLivery API",
    description="API to manage agencies, clients and AI agents.",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    # The configured frontend origin (a real domain in production) plus any
    # localhost/127.0.0.1 port, so changing WEB_PORT never breaks local dev.
    allow_origins=[settings.frontend_url],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(agency.router, prefix="/api")
app.include_router(clients.router, prefix="/api")
app.include_router(industries.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(webchat.router, prefix="/api")
app.include_router(agent_tools.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(mobile.router, prefix="/api")
app.include_router(portal.router, prefix="/api")
app.include_router(whatsapp.router, prefix="/api")
app.include_router(whatsapp.internal_router, prefix="/api")
app.include_router(whatsapp_cloud.router, prefix="/api")
app.include_router(whatsapp_cloud_webhook.public_router, prefix="/api")
app.include_router(widget.router, prefix="/api")
app.include_router(domains.public_router, prefix="/api")
