import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def new_public_id() -> str:
    return uuid.uuid4().hex


def new_domain_token() -> str:
    return uuid.uuid4().hex


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    brand_color: Mapped[str] = mapped_column(String(20), default="#075985")
    logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    users: Mapped[list["User"]] = relationship(back_populates="agency", cascade="all, delete-orphan")

    @property
    def logo_url(self) -> str | None:
        return f"/api/agency/logo?v={int(self.created_at.timestamp())}" if self.logo_data else None


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    agency: Mapped[Agency] = relationship(back_populates="users")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    industry: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    general_context: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional per-client logo, shown in the widget and portal (falls back to
    # the agency logo). Bytes stored in Postgres like the agency logo.
    logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    logo_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    portal_slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    portal_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    portal_title: Mapped[str] = mapped_column(String(180), default="")
    # Optional custom domain for this client's portal. Verified via a DNS TXT
    # challenge; only verified domains are routed and get an on-demand cert.
    portal_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    portal_domain_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    portal_domain_token: Mapped[str] = mapped_column(String(64), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    agents: Mapped[list["Agent"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    whatsapp_channel: Mapped["WhatsAppChannel | None"] = relationship(
        back_populates="client", cascade="all, delete-orphan", uselist=False
    )
    whatsapp_cloud_channel: Mapped["WhatsAppCloudChannel | None"] = relationship(
        back_populates="client", cascade="all, delete-orphan", uselist=False
    )
    portal_users: Mapped[list["PortalUser"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    @property
    def logo_url(self) -> str | None:
        return f"/api/clients/{self.id}/logo?v={int(self.updated_at.timestamp())}" if self.logo_mime else None


class ProviderCredential(Base):
    """One AI provider API key per agency (bring your own key). provider is
    "openai" or "anthropic"; the base URL is resolved from the provider."""

    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("agency_id", "provider", name="uq_provider_credentials_agency_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    # Structured business brief. Optional guided fields that compose into the
    # system prompt alongside the free-form instructions.
    brief_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_products: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_audience: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_policies: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_goal: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_dos: Mapped[str] = mapped_column(Text, default="", server_default="")
    brief_donts: Mapped[str] = mapped_column(Text, default="", server_default="")
    # AI provider ("openai" or "anthropic"); the agency's key for that provider is used.
    provider: Mapped[str] = mapped_column(String(30), default="openai", server_default="openai")
    model: Mapped[str] = mapped_column(String(180), default="")
    # IANA timezone (e.g. "America/Bogota"); injected into the system prompt so
    # the agent knows the local date/time. "UTC" when unset.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    manual_context: Mapped[str] = mapped_column(Text, default="")
    # Generation settings. Sampling params are applied best-effort by the AI
    # service (models that reject them fall back to their defaults).
    temperature: Mapped[float] = mapped_column(Float, default=0.7, server_default="0.7")
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, server_default="2048")
    # How many past messages are kept as conversation memory.
    memory_limit: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    # Multimodal capabilities. When enabled, inbound images are described by a
    # vision model and inbound audio is transcribed before reaching the agent.
    image_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    image_model: Mapped[str] = mapped_column(String(180), default="", server_default="")
    audio_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    audio_model: Mapped[str] = mapped_column(String(180), default="whisper-1", server_default="whisper-1")
    # Embeddable web chat widget.
    widget_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    widget_public_id: Mapped[str] = mapped_column(String(64), default=new_public_id, unique=True, index=True)
    widget_greeting: Mapped[str] = mapped_column(Text, default="", server_default="")
    widget_color: Mapped[str] = mapped_column(String(20), default="", server_default="")
    widget_position: Mapped[str] = mapped_column(String(10), default="right", server_default="right")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    client: Mapped[Client] = relationship(back_populates="agents")
    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    qa_pairs: Mapped[list["AgentQA"]] = relationship(back_populates="agent", cascade="all, delete-orphan", order_by="AgentQA.position")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    whatsapp_channels: Mapped[list["WhatsAppChannel"]] = relationship(back_populates="agent")
    whatsapp_cloud_channels: Mapped[list["WhatsAppCloudChannel"]] = relationship(back_populates="agent")
    tools: Mapped[list["AgentTool"]] = relationship(back_populates="agent", cascade="all, delete-orphan", order_by="AgentTool.created_at")


class AgentTool(Base):
    """A custom tool the agent can call: a user-defined HTTP endpoint
    ("http") or an external MCP server ("mcp")."""

    __tablename__ = "agent_tools"
    __table_args__ = (UniqueConstraint("agent_id", "name", name="uq_agent_tools_agent_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # HTTP endpoint (may contain {param} path placeholders) or MCP server URL.
    url: Mapped[str] = mapped_column(Text, default="")
    # HTTP tools only.
    http_method: Mapped[str] = mapped_column(String(10), default="GET")
    prompt_instructions: Mapped[str] = mapped_column(Text, default="")
    body_params: Mapped[list] = mapped_column(JSON, default=list)
    query_params: Mapped[list] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    # MCP servers only. cached_tools holds the last list_tools result so chat
    # requests never block on discovery; refreshed on save/test-connection.
    transport: Mapped[str] = mapped_column(String(20), default="streamable_http")
    cached_tools: Mapped[list] = mapped_column(JSON, default=list)
    tools_cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The full auth headers dict, encrypted at rest; never returned by the API.
    encrypted_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    agent: Mapped[Agent] = relationship(back_populates="tools")


class WhatsAppChannel(Base):
    __tablename__ = "whatsapp_channels"
    __table_args__ = (UniqueConstraint("client_id", name="uq_whatsapp_channels_client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    encrypted_auth_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_qr: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    client: Mapped[Client] = relationship(back_populates="whatsapp_channel")
    agent: Mapped[Agent] = relationship(back_populates="whatsapp_channels")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="whatsapp_channel")


class WhatsAppCloudChannel(Base):
    """Official WhatsApp Business Cloud API channel (Meta Graph API). Coexists
    with the Baileys channel: a client can have one of each, on different
    numbers. Credentials are provided manually (bring your own Meta app)."""

    __tablename__ = "whatsapp_cloud_channels"
    __table_args__ = (UniqueConstraint("client_id", name="uq_whatsapp_cloud_channels_client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    phone_number_id: Mapped[str] = mapped_column(String(80), default="", server_default="")
    waba_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_app_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Token the owner pastes into their Meta app's webhook config; it must be
    # re-displayable, so it is stored in plain text like portal_domain_token.
    webhook_verify_token: Mapped[str] = mapped_column(String(64), default=new_public_id, server_default="")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    client: Mapped[Client] = relationship(back_populates="whatsapp_cloud_channel")
    agent: Mapped[Agent] = relationship(back_populates="whatsapp_cloud_channels")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="whatsapp_cloud_channel")


class AgentQA(Base):
    __tablename__ = "agent_qa"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    agent: Mapped[Agent] = relationship(back_populates="qa_pairs")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="processed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    agent: Mapped[Agent] = relationship(back_populates="documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    # Embedding vector stored as a JSON array of floats (portable across any
    # Postgres; similarity is computed in Python). Swap to pgvector at scale.
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(180))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("whatsapp_channel_id", "external_chat_id", name="uq_conversations_whatsapp_chat"),
        UniqueConstraint(
            "whatsapp_cloud_channel_id", "external_chat_id", name="uq_conversations_whatsapp_cloud_chat"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), default="New conversation")
    mode: Mapped[str] = mapped_column(String(30), default="ai")
    channel: Mapped[str] = mapped_column(String(40), default="playground")
    whatsapp_channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_channels.id", ondelete="CASCADE"), nullable=True, index=True
    )
    whatsapp_cloud_channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_cloud_channels.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    operator_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    agent: Mapped[Agent] = relationship(back_populates="conversations")
    whatsapp_channel: Mapped[WhatsAppChannel | None] = relationship(back_populates="conversations")
    whatsapp_cloud_channel: Mapped[WhatsAppCloudChannel | None] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "external_message_id", name="uq_messages_conversation_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    # What the LLM sees for this message when it differs from the displayed
    # content (e.g. an image description or audio transcript for a media
    # message whose visible content is just the caption).
    llm_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    # Tool usage behind an assistant reply: [{name, arguments, result_preview, is_error}].
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sender_type: Mapped[str] = mapped_column(String(30), default="visitor")
    sender_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The business's emoji reaction to this (visitor) message, mirrored in the
    # portal so operators see the same gesture the customer saw on WhatsApp.
    reaction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Set when this reply quotes a specific earlier message (swipe-to-reply).
    quoted_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list["MessageAttachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="MessageAttachment.created_at"
    )


class MessageAttachment(Base):
    """Original media file behind a chat message (image, voice note, document).

    Bytes live in Postgres like KnowledgeDocument/Agency.logo_data; the LLM
    never reads this table — it gets the text resolved into Message.llm_content.
    """

    __tablename__ = "message_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # image | audio | file
    mime: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    message: Mapped[Message] = relationship(back_populates="attachments")

class PortalUser(Base):
    """A person at the client's business who can answer from the portal.

    Before this table a portal had a single e-mail and password shared by
    everyone at the business. That is workable in a browser and breaks down with
    push: you cannot tell which phone to notify, who replied, or revoke one
    employee. Since 0021 this is the only portal login; the migration carried
    every legacy credential over, so nobody's password stopped working.
    """

    __tablename__ = "portal_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    client: Mapped["Client"] = relationship(back_populates="portal_users")
    devices: Mapped[list["PushDevice"]] = relationship(back_populates="portal_user", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("client_id", "email", name="uq_portal_users_client_email"),)


class PushDevice(Base):
    """A phone that asked to be told when a conversation needs a person.

    The registry is deliberately provider-agnostic: ``token`` is whatever the
    configured notification provider needs to reach this install (a device
    token, a subscription id, a topic), and ``provider`` records which one
    issued it so a server that changes providers ignores stale rows instead of
    sending them somewhere meaningless.

    The token is unique, so re-registering the same install updates the row
    rather than accumulating duplicates. Rows die with their user or client.
    """

    __tablename__ = "push_devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="")
    platform: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    portal_user: Mapped["PortalUser | None"] = relationship(back_populates="devices")
