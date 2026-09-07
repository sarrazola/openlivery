import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SocialChannelUpdate(BaseModel):
    agent_id: uuid.UUID
    external_account_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9]+$")
    app_id: str | None = Field(default=None, max_length=64, pattern=r"^[0-9]*$")
    access_token: str | None = Field(default=None, max_length=8192)
    app_secret: str | None = Field(default=None, max_length=512)
    human_agent_enabled: bool | None = None


class SocialChannelOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    agent_id: uuid.UUID
    provider: Literal["instagram", "messenger"]
    external_account_id: str | None = None
    app_id: str | None = None
    display_name: str | None = None
    username: str | None = None
    status: str
    is_enabled: bool
    token_expires_at: datetime | None = None
    last_error: str | None = None
    human_agent_enabled: bool
    connection_source: str
    granted_scopes: list[str] = []
    has_access_token: bool
    has_app_secret: bool
    webhook_url: str
    webhook_verify_token: str | None = None
    last_connected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SocialOAuthStart(BaseModel):
    client_id: uuid.UUID
    agent_id: uuid.UUID
    next_path: str | None = Field(default=None, max_length=300)


class SocialOAuthComplete(BaseModel):
    setup_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")
    external_account_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9]+$")
