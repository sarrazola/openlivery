import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WhatsAppCloudChannelUpdate(BaseModel):
    agent_id: uuid.UUID
    phone_number_id: str | None = Field(default=None, max_length=80)
    waba_id: str | None = Field(default=None, max_length=80)
    # Secrets are write-only: omitted or blank values keep the stored ones.
    access_token: str | None = Field(default=None, max_length=4000)
    app_secret: str | None = Field(default=None, max_length=255)


class WhatsAppCloudChannelOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    phone_number: str | None
    display_name: str | None
    phone_number_id: str
    waba_id: str | None
    coexistence: bool = False
    coexistence_sync: dict = Field(default_factory=dict)
    has_access_token: bool
    has_app_secret: bool
    webhook_url: str
    webhook_verify_token: str
    last_error: str | None
    is_enabled: bool
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime
