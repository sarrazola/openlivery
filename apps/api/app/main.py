from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
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
    mobile,
    portal,
    providers,
    whatsapp,
    whatsapp_cloud,
    whatsapp_cloud_webhook,
    widget,
)


settings = get_settings()
app = FastAPI(
    title="OpenLivery API",
    description="API to manage agencies, clients and AI agents.",
    version="0.3.0",
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
app.include_router(agents.router, prefix="/api")
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
