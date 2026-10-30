import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CallAccountIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=400)
    account_sid: str | None = Field(default=None, max_length=80)
    auth_token: str | None = Field(default=None, max_length=200)


class CallAccountOut(BaseModel):
    provider: str
    configured: bool
    stored: bool
    # Where calls get this account from: the agency's own, the deployment's, or none.
    source: str = "none"
    secret_hint: str = ""
    last_error: str | None = None


class CallAccountTest(BaseModel):
    ok: bool
    message: str


class PhoneVoiceOut(BaseModel):
    voice_id: str
    name: str
    accent: str = ""
    gender: str = ""
    description: str = ""
    preview_url: str | None = None


class PhoneModelOut(BaseModel):
    id: str
    label: str
    realtime: bool


class CarrierNumberOut(BaseModel):
    id: str
    phone_number: str
    name: str = ""


class PhoneLineCreate(BaseModel):
    agent_id: uuid.UUID
    provider: str = Field(pattern="^(twilio|telnyx)$")
    provider_number_id: str = Field(min_length=1, max_length=80)
    phone_number: str = Field(min_length=4, max_length=32)
    transfer_number: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=80)


class PhoneLineUpdate(BaseModel):
    agent_id: uuid.UUID | None = None
    transfer_number: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=80)
    is_enabled: bool | None = None


class PhoneLineOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    agent_id: uuid.UUID
    label: str | None
    phone_number: str
    provider: str
    provider_number_id: str | None
    transfer_number: str | None
    status: str
    is_enabled: bool
    last_error: str | None
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime
