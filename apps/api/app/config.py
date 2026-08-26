from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


APP_DIR = Path(__file__).resolve().parents[1]   # apps/api
REPO_ROOT = Path(__file__).resolve().parents[3]  # monorepo root (used for a shared local .env)


class Settings(BaseSettings):
    app_name: str = "OpenLivery API"
    database_url: str = "postgresql+psycopg://openlivery:openlivery@localhost:5432/openlivery"
    secret_key: str = "dev-local-change-this-key-please"
    encryption_key: str = "dev-local-change-this-key-too"
    frontend_url: str = "http://localhost:3000"
    access_token_minutes: int = 60 * 24 * 7
    # Session cookie flags. Defaults suit local HTTP; set cookie_secure=true (and
    # cookie_samesite=none when the frontend and API are on different sites)
    # behind HTTPS in production.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    # Rate limiting on public/unauthenticated endpoints (per client IP). Disable
    # only for tests or when a proxy in front already enforces limits.
    rate_limit_enabled: bool = True
    # A self-hosted instance is single-agency by default: the first registration
    # creates the owner agency and closes public sign-up (like n8n's owner
    # setup). Enable only when one deployment must host many agencies.
    allow_multi_agency: bool = False
    # SSRF guard for agent HTTP tools: URLs resolving to private/loopback
    # addresses are rejected. Enable only on self-hosted deployments that need
    # tools to reach internal services.
    tools_allow_private_urls: bool = False
    storage_dir: Path = APP_DIR / "storage"
    backend_url: str = "http://localhost:8000"
    whatsapp_bridge_url: str = "http://localhost:3101"
    whatsapp_bridge_token: str = "dev-local-change-this-bridge-token"
    # Meta Graph API root used by the WhatsApp Cloud API channel; override to
    # point at a mock server in tests.
    meta_graph_base_url: str = "https://graph.facebook.com/v23.0"

    # Push notifications for the mobile app. "none" (the default) sends nothing
    # and needs no account with anyone; "webhook" POSTs each event to
    # push_webhook_url so you can route it through whatever you already use.
    # Deployments may register further providers at startup — see
    # app/services/notifications.py and docs/push-notifications.md.
    push_provider: str = "none"
    push_webhook_url: str = ""
    push_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", APP_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
