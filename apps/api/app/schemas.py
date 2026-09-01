import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    agency_name: str = Field(min_length=2, max_length=180)
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AgencyOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    brand_color: str
    logo_url: str | None = None


class AgencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    slug: str | None = Field(default=None, min_length=2, max_length=180)
    brand_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    agency: AgencyOut


class ClientBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    industry: str = Field(default="", max_length=160)
    description: str = ""
    general_context: str = ""
    is_active: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    industry: str | None = None
    description: str | None = None
    general_context: str | None = None
    is_active: bool | None = None


class ClientPortalUpdate(BaseModel):
    portal_enabled: bool | None = None
    portal_slug: str | None = Field(default=None, min_length=2, max_length=180)
    portal_title: str | None = Field(default=None, max_length=180)


class AgentSummary(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    is_active: bool


class ClientOut(ORMModel):
    id: uuid.UUID
    name: str
    industry: str
    description: str
    general_context: str
    is_active: bool
    portal_slug: str
    portal_enabled: bool
    portal_title: str
    portal_domain: str | None
    portal_domain_verified: bool
    logo_url: str | None = None
    created_at: datetime
    updated_at: datetime
    agents: list[AgentSummary] = []


class PortalUserCreate(BaseModel):
    """A person at the client's business who can answer from the portal or app."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=160)


class PortalUserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=160)
    is_active: bool | None = None


class PortalUserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    is_active: bool
    devices: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientDomainSet(BaseModel):
    # A DNS hostname, e.g. "chat.brand.com". Lowercased and validated as a host.
    # No look-around: pydantic v2's regex engine does not support it.
    domain: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$",
    )


class ClientDomainOut(BaseModel):
    domain: str | None
    verified: bool
    # DNS records the operator/client must create.
    txt_host: str | None
    txt_value: str | None


class ProviderKeyUpdate(BaseModel):
    api_key: str = Field(min_length=1)


class ProviderOut(BaseModel):
    provider: str
    label: str
    configured: bool
    api_key_masked: str = ""


class AgentBase(BaseModel):
    client_id: uuid.UUID
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    instructions: str = ""
    personality: str = ""
    brief_summary: str = ""
    brief_products: str = ""
    brief_audience: str = ""
    brief_policies: str = ""
    brief_goal: str = ""
    brief_dos: str = ""
    brief_donts: str = ""
    model: str = ""
    provider: str = Field(default="openai", pattern=r"^(openai|anthropic)$")
    timezone: str = Field(default="UTC", max_length=64)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32000)
    memory_limit: int = Field(default=30, ge=0, le=200)
    image_enabled: bool = False
    image_model: str = Field(default="", max_length=180)
    audio_enabled: bool = False
    audio_model: str = Field(default="whisper-1", max_length=180)
    widget_enabled: bool = False
    widget_greeting: str = Field(default="", max_length=2000)
    widget_color: str = Field(default="", max_length=20)
    widget_position: str = Field(default="right", pattern=r"^(right|left)$")
    is_active: bool = True


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    client_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    instructions: str | None = None
    personality: str | None = None
    brief_summary: str | None = None
    brief_products: str | None = None
    brief_audience: str | None = None
    brief_policies: str | None = None
    brief_goal: str | None = None
    brief_dos: str | None = None
    brief_donts: str | None = None
    model: str | None = None
    provider: str | None = Field(default=None, pattern=r"^(openai|anthropic)$")
    timezone: str | None = Field(default=None, max_length=64)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    memory_limit: int | None = Field(default=None, ge=0, le=200)
    image_enabled: bool | None = None
    image_model: str | None = Field(default=None, max_length=180)
    audio_enabled: bool | None = None
    audio_model: str | None = Field(default=None, max_length=180)
    widget_enabled: bool | None = None
    widget_greeting: str | None = Field(default=None, max_length=2000)
    widget_color: str | None = Field(default=None, max_length=20)
    widget_position: str | None = Field(default=None, pattern=r"^(right|left)$")
    is_active: bool | None = None


class AgentOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    provider: str
    name: str
    description: str
    instructions: str
    personality: str
    brief_summary: str
    brief_products: str
    brief_audience: str
    brief_policies: str
    brief_goal: str
    brief_dos: str
    brief_donts: str
    model: str
    timezone: str
    manual_context: str
    temperature: float
    max_tokens: int
    memory_limit: int
    image_enabled: bool
    image_model: str
    audio_enabled: bool
    audio_model: str
    widget_enabled: bool
    widget_public_id: str
    widget_greeting: str
    widget_color: str
    widget_position: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    client: ClientOut


class ManualContextRequest(BaseModel):
    manual_context: str


class QAPairCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)


class QAPairOut(ORMModel):
    id: uuid.UUID
    question: str
    answer: str


class ModelCatalogOut(BaseModel):
    id: str
    provider: str
    label: str
    family: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    input_price_per_1k: float
    output_price_per_1k: float
    badge: str = ""
    note: str = ""


class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    status: str
    error_message: str | None
    created_at: datetime
    character_count: int = 0


class ConversationCreate(BaseModel):
    agent_id: uuid.UUID


class ConversationOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    mode: str
    channel: str
    external_chat_id: str | None = None
    contact_name: str | None = None
    contact_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    status: str = "open"
    resolved_at: datetime | None = None
    first_reply_at: datetime | None = None
    taken_over_at: datetime | None = None
    waiting_since: datetime | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    # WhatsApp Cloud API: free-form replies are allowed until this moment
    # (24 h after the contact's last message). None on other channels or
    # when the contact never wrote; ``reply_window_open`` says what applies.
    reply_window_until: datetime | None = None
    reply_window_open: bool = True
    preview: str = ""
    unread: bool = False
    unread_count: int = 0
    # When the contact last wrote; the inbox shows this so the row's time
    # means "waiting since", not "our last activity".
    last_inbound_at: datetime | None = None


class SourceOut(BaseModel):
    id: str
    filename: str
    excerpt: str = ""


class AttachmentOut(ORMModel):
    id: uuid.UUID
    kind: str
    mime: str
    filename: str | None = None
    size_bytes: int = 0


class MessageOut(ORMModel):
    id: uuid.UUID
    role: str
    kind: str = "message"
    activity: dict | None = None
    content: str
    sources: list[dict] = []
    tool_calls: list[dict] | None = None
    sender_type: str
    sender_name: str | None
    external_message_id: str | None = None
    delivery_status: str | None = None
    delivery_error: str | None = None
    reaction: str | None = None
    incoming_reaction: str | None = None
    quoted_message_id: uuid.UUID | None = None
    created_at: datetime
    attachments: list[AttachmentOut] = []


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class ConversationInboxOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    client_id: uuid.UUID
    title: str
    contact_name: str | None = None
    channel: str
    mode: str
    preview: str = ""
    unread: bool = False
    unread_count: int = 0
    updated_at: datetime
    last_inbound_at: datetime | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    # Reply quoting this earlier message of the conversation (swipe-to-reply).
    quoted_message_id: uuid.UUID | None = None


class ReactionRequest(BaseModel):
    # Empty string removes the reaction.
    emoji: str = Field(default="", max_length=16)


class ConversationModeUpdate(BaseModel):
    mode: str = Field(pattern=r"^(ai|human)$")


class ConversationStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(open|resolved)$")


class ConversationAssignmentUpdate(BaseModel):
    # The portal user who takes the conversation. Letting go of it means
    # returning it to the AI, not leaving it without an owner.
    assignee_id: uuid.UUID | None = None


class PortalMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    availability: str = "online"


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    availability: str = "online"


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str = ""
    strategy: str = "round_robin"
    channels: list[str] = []
    is_default: bool = False
    members: list[TeamMemberOut] = []
    open_count: int = 0
    unassigned_count: int = 0


class TeamUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    strategy: str = Field(default="round_robin", pattern=r"^(round_robin|least_busy)$")
    channels: list[str] = []
    is_default: bool = False
    member_ids: list[uuid.UUID] = []


class ConversationTeamUpdate(BaseModel):
    team_id: uuid.UUID | None = None


class EscalationRuleIn(BaseModel):
    # WHEN, in the business's words; the model evaluates it contextually.
    condition: str = Field(min_length=1, max_length=2000)
    # WHERE, a hard reference: exactly one of these two.
    team_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    is_active: bool = True


class EscalationRuleOut(BaseModel):
    id: uuid.UUID
    position: int
    condition: str
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    is_active: bool = True
    # The destination was deleted; the rule no longer routes anywhere.
    broken: bool = False


class EscalationConfigIn(BaseModel):
    # Destination of the built-in triggers; at most one of the two. Both empty
    # falls back to the channel's tray, then the default tray.
    default_team_id: uuid.UUID | None = None
    default_assignee_id: uuid.UUID | None = None
    rules: list[EscalationRuleIn] = []


class EscalationConfigOut(BaseModel):
    default_team_id: uuid.UUID | None = None
    default_team_name: str | None = None
    default_assignee_id: uuid.UUID | None = None
    default_assignee_name: str | None = None
    rules: list[EscalationRuleOut] = []


class PortalAvailabilityUpdate(BaseModel):
    availability: str = Field(pattern=r"^(online|away)$")


class PortalChannelOut(BaseModel):
    channel: str
    status: str
    phone_number: str | None = None
    display_name: str | None = None
    supports_templates: bool = False


class TemplateOut(BaseModel):
    id: str | None = None
    name: str
    language: str
    category: str
    status: str
    body: str
    footer: str = ""
    variables: int = 0
    rejected_reason: str | None = None


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    language: str = Field(default="es", min_length=2, max_length=10)
    category: str = Field(default="UTILITY", pattern=r"^(UTILITY|MARKETING)$")
    body: str = Field(min_length=1, max_length=1024)
    footer: str = Field(default="", max_length=60)
    examples: list[str] = []


class TemplateSend(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    language: str = Field(min_length=2, max_length=10)
    variables: list[str] = []


class CannedResponseOut(ORMModel):
    id: uuid.UUID
    shortcut: str
    content: str
    updated_at: datetime


class CannedResponseCreate(BaseModel):
    shortcut: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    content: str = Field(min_length=1, max_length=4000)


class CannedResponseUpdate(BaseModel):
    shortcut: str | None = Field(default=None, min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    content: str | None = Field(default=None, min_length=1, max_length=4000)


class ConversationStart(BaseModel):
    # whatsapp_cloud needs a template; whatsapp (QR) takes free text.
    channel: str | None = Field(default=None, pattern=r"^(whatsapp|whatsapp_cloud)$")
    template: TemplateSend | None = None
    text: str | None = Field(default=None, max_length=4000)


class ContactCreate(BaseModel):
    name: str = Field(default="", max_length=180)
    phone: str = Field(min_length=7, max_length=40)
    email: EmailStr | None = None
    notes: str = Field(default="", max_length=5000)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, min_length=7, max_length=40)
    email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None = None
    email: str | None = None
    notes: str = ""
    created_at: datetime
    updated_at: datetime
    conversation_count: int = 0
    open_count: int = 0
    last_activity_at: datetime | None = None


class ContactMergeRequest(BaseModel):
    # The surviving contact; the one addressed by the URL is folded into it
    # and deleted.
    primary_contact_id: uuid.UUID


class PortalInboxSummary(BaseModel):
    open: int = 0
    resolved: int = 0
    human: int = 0
    ai: int = 0
    unread: int = 0
    mine: int = 0
    unassigned: int = 0


class PortalLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PortalPublicOut(BaseModel):
    client_name: str
    portal_title: str
    portal_slug: str
    agency_name: str
    agency_brand_color: str
    agency_logo_url: str | None
    client_logo_url: str | None = None


class PortalSessionOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    portal_slug: str
    agency_name: str
    # The person behind the session; absent on sessions that predate portal users.
    user_id: uuid.UUID | None = None
    user_name: str | None = None


class DashboardOut(BaseModel):
    clients: int
    active_clients: int
    agents: int
    active_agents: int
    conversations: int
    channels: int
    connected_channels: int
    recent_agents: list[AgentSummary]


class DailyPoint(BaseModel):
    date: str
    count: int


class TopAgent(BaseModel):
    id: uuid.UUID
    name: str
    conversations: int


class ModelUsage(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int


class DashboardMetrics(BaseModel):
    messages: int
    human_conversations: int
    by_channel: dict[str, int]
    daily_conversations: list[DailyPoint]
    top_agents: list[TopAgent]
    tokens_in: int
    tokens_out: int
    usage_by_model: list[ModelUsage]


class WhatsAppChannelUpdate(BaseModel):
    agent_id: uuid.UUID


class WhatsAppChannelOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    phone_number: str | None
    display_name: str | None
    qr_code: str | None = None
    last_error: str | None
    is_enabled: bool
    has_session: bool = False
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WhatsAppInternalAuth(BaseModel):
    auth_state: dict


class WhatsAppInternalStatus(BaseModel):
    status: str = Field(pattern=r"^(disconnected|connecting|qr|connected|reconnecting|error)$")
    phone_number: str | None = None
    display_name: str | None = None
    qr_code: str | None = None
    error: str | None = None


class WidgetConfigOut(BaseModel):
    title: str
    greeting: str
    color: str
    position: str
    agency_name: str
    # Public logo shown in the widget header: the client's own logo when set,
    # otherwise the agency logo.
    logo_url: str | None = None


class WidgetMessageIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=8000)


class WidgetMessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime | None = None
    attachments: list[AttachmentOut] = []


class WidgetReply(BaseModel):
    mode: str
    reply: str | None = None
    reply_at: datetime | None = None
    messages: list[WidgetMessageOut] = []


class WhatsAppInbound(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    remote_jid: str = Field(min_length=1, max_length=255)
    sender_name: str | None = Field(default=None, max_length=180)
    text: str = Field(default="", max_length=50000)
    # Optional media (base64) for voice notes / images, processed by the agent's
    # audio/image capabilities before reaching the model.
    media_kind: str | None = Field(default=None, pattern=r"^(image|audio|video)$")
    media_base64: str | None = None
    media_mime: str | None = Field(default=None, max_length=100)
    # External id of the message the visitor replied to (swipe-to-reply).
    quoted_external_id: str | None = Field(default=None, max_length=255)


class WhatsAppInboundReaction(BaseModel):
    remote_jid: str = Field(min_length=1, max_length=255)
    # External id of the message the visitor reacted to.
    target_external_id: str = Field(min_length=1, max_length=255)
    # Empty string removes the reaction.
    emoji: str = Field(default="", max_length=16)


class WhatsAppInboundResult(BaseModel):
    accepted: bool
    reply: str | None = None
    conversation_id: uuid.UUID | None = None
    mode: str | None = None
    outbound_message_id: uuid.UUID | None = None
    # External id of the visitor message the reply quotes (swipe-to-reply).
    quote_external_id: str | None = None


class WhatsAppOutboundConfirm(BaseModel):
    message_id: uuid.UUID
    external_message_id: str = Field(min_length=1, max_length=255)
