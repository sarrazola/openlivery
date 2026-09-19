export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  agency: Agency;
};

export type Agency = { id: string; name: string; slug: string; brand_color: string; logo_url: string | null };

export type AgentSummary = { id: string; name: string; is_active: boolean };

export type IndustryLabel = { en: string; es: string };
export type BusinessType = { code: string; label: IndustryLabel };
export type Industry = { code: string; label: IndustryLabel; types: BusinessType[] };

export type Client = {
  id: string;
  name: string;
  industry: string;
  business_type: string;
  business_custom: string;
  timezone: string;
  is_active: boolean;
  portal_slug: string;
  portal_enabled: boolean;
  portal_title: string;
  portal_domain: string | null;
  portal_domain_verified: boolean;
  logo_url: string | null;
  agents: AgentSummary[];
  created_at: string;
  updated_at: string;
};

export type PortalRole = "admin" | "agent";
export type PortalUser = {
  id: string;
  name: string;
  email: string;
  role: PortalRole;
  is_active: boolean;
  devices: number;
  created_at: string;
};

export type ClientDomain = {
  domain: string | null;
  verified: boolean;
  txt_host: string | null;
  txt_value: string | null;
};

export type Agent = {
  id: string;
  client_id: string;
  provider: string;
  name: string;
  instructions: string;
  personality: string;
  brief_summary: string;
  brief_products: string;
  brief_audience: string;
  brief_policies: string;
  brief_dos: string;
  brief_donts: string;
  model: string;
  prompt_language: "en" | "es";
  temperature: number;
  max_tokens: number;
  memory_limit: number;
  phone_handover_minutes: number;
  reply_delay_min_seconds: number;
  reply_delay_max_seconds: number;
  image_enabled: boolean;
  image_model: string;
  audio_enabled: boolean;
  audio_model: string;
  embedding_model: string;
  is_active: boolean;
  client: Client;
  created_at: string;
  updated_at: string;
};

export type Provider = {
  provider: string;
  label: string;
  configured: boolean;
  api_key_masked: string;
};

export type ProviderTest = { ok: boolean; message: string; models: string[] };

export type KnowledgeDocument = {
  id: string;
  filename: string;
  status: "processed" | "error" | "pending";
  error_message: string | null;
  character_count: number;
  created_at: string;
  // Embedding model of the stored chunks; null when nothing is indexed.
  indexed_model: string | null;
  chunk_count: number;
};
export type EmbeddingModelInfo = { id: string; provider: string; label: string; context_window: number; input_price_per_1k: number; note: string };

export type QAPair = { id: string; question: string; answer: string };

export type ToolParam = { name: string; type: "string" | "number" | "integer" | "boolean"; description: string; required: boolean };
export type McpCachedTool = { name: string; description: string; input_schema?: Record<string, unknown>; read_only?: boolean; destructive?: boolean };
export type AgentTool = {
  id: string;
  agent_id: string;
  type: "http" | "mcp";
  name: string;
  description: string;
  enabled: boolean;
  url: string;
  http_method: string;
  prompt_instructions: string;
  body_params: ToolParam[];
  query_params: ToolParam[];
  timeout_seconds: number;
  transport: "sse" | "streamable_http";
  cached_tools: McpCachedTool[];
  tools_cached_at: string | null;
  // null: every cached tool is exposed; a list restricts the server to it.
  enabled_tools: string[] | null;
  has_headers: boolean;
  created_at: string;
  updated_at: string;
};
export type ToolCallMeta = { name: string; arguments: Record<string, unknown>; result_preview: string; is_error: boolean };

export type Source = { id: string; filename: string; excerpt: string };
export type Attachment = { id: string; kind: "image" | "audio" | "video" | "file"; mime: string; filename: string | null; size_bytes: number };
export type Message = { id: string; role: "user" | "assistant" | "system"; kind?: "message" | "activity"; delivery_status?: "pending" | "sent" | "delivered" | "read" | "failed" | "unknown" | null; delivery_error?: string | null; activity?: { event: string; hours?: number | string; assignee?: string; from?: string; team?: string; target?: string; reason?: string; tag?: string } | null; content: string; sources: Source[]; tool_calls?: ToolCallMeta[] | null; sender_type: "visitor" | "ai" | "human"; sender_name: string | null; reaction?: string | null; incoming_reaction?: string | null; quoted_message_id?: string | null; created_at: string; attachments?: Attachment[] };

export type ConversationInbox = {
  id: string;
  agent_id: string;
  agent_name: string;
  client_id: string;
  title: string;
  contact_name: string | null;
  channel: string;
  account_label?: string | null;
  mode: "ai" | "human";
  preview: string;
  unread: boolean;
  unread_count: number;
  updated_at: string;
  last_inbound_at?: string | null;
};
export type PortalMember = { id: string; name: string; email: string; availability: "online" | "away" };
export type TeamMember = { id: string; name: string; email: string; availability: "online" | "away" };
export type Team = {
  id: string;
  name: string;
  description: string;
  strategy: "round_robin" | "least_busy";
  channels: string[];
  is_default: boolean;
  members: TeamMember[];
  open_count: number;
  unassigned_count: number;
};
export type Conversation = {
  id: string;
  client_id: string;
  agent_id: string;
  title: string;
  mode: "ai" | "human";
  status?: "open" | "resolved";
  resolved_at?: string | null;
  archived_at?: string | null;
  first_reply_at?: string | null;
  taken_over_at?: string | null;
  phone_pause_until?: string | null;
  waiting_since?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  team_id?: string | null;
  team_name?: string | null;
  reply_window_until?: string | null;
  reply_window_open?: boolean;
  human_reply_window_open?: boolean;
  human_reply_window_until?: string | null;
  reply_block_reason?: string | null;
  social_channel_id?: string | null;
  account_label?: string | null;
  channel_capabilities?: ChannelCapabilities;
  channel: string;
  external_chat_id: string | null;
  contact_name: string | null;
  contact_email?: string | null;
  contact_id?: string | null;
  created_at: string;
  updated_at: string;
  last_inbound_at?: string | null;
  preview?: string;
  unread?: boolean;
  unread_count?: number;
  messages?: Message[];
};

export type WhatsAppChannel = {
  id: string;
  client_id: string;
  agent_id: string;
  status: "disconnected" | "connecting" | "qr" | "connected" | "reconnecting" | "error";
  phone_number: string | null;
  display_name: string | null;
  label: string | null;
  qr_code: string | null;
  last_error: string | null;
  is_enabled: boolean;
  has_session: boolean;
  last_connected_at: string | null;
  created_at: string;
  updated_at: string;
};

export type WidgetChannel = {
  id: string;
  client_id: string;
  agent_id: string;
  public_id: string;
  is_enabled: boolean;
  greeting: string;
  color: string;
  position: "right" | "left";
  created_at: string;
  updated_at: string;
};

export type WhatsAppCloudChannel = {
  id: string;
  client_id: string;
  agent_id: string;
  status: "disconnected" | "connected" | "error";
  phone_number: string | null;
  display_name: string | null;
  label: string | null;
  phone_number_id: string;
  waba_id: string | null;
  coexistence: boolean;
  coexistence_sync: {
    started_at?: string;
    offboarded_at?: string;
    contacts?: { status: string; request_id?: string; error?: string; last_received_at?: string };
    media?: { status: string; error?: string };
    history?: { status: string; progress?: number; errors?: number; request_id?: string; error?: string };
  };
  quality_rating: string | null;
  messaging_limit: string | null;
  has_access_token: boolean;
  has_app_secret: boolean;
  webhook_url: string;
  webhook_verify_token: string;
  last_error: string | null;
  is_enabled: boolean;
  last_connected_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TemplateHeader = {
  format: "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT" | "LOCATION" | string;
  text: string;
  parameters: string[];
};

export type TemplateButton = {
  type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | "COPY_CODE" | string;
  text: string;
  url: string;
  phone_number: string;
  example: string;
  /** Takes a value at send time: a URL suffix or the code to copy. */
  dynamic: boolean;
};

export type Template = {
  id: string | null;
  name: string;
  language: string;
  category: string;
  status: "APPROVED" | "PENDING" | "REJECTED" | string;
  parameter_format: "NAMED" | "POSITIONAL" | string;
  header: TemplateHeader | null;
  body: string;
  footer: string;
  buttons: TemplateButton[];
  /** Body variables in order; `variables` is their count. */
  parameters: string[];
  variables: number;
  rejected_reason: string | null;
};

export type TemplateSend = {
  name: string;
  language: string;
  /** Body values in the order of the template's parameters. */
  variables: string[];
  /** The header's variable, or the https link of its media. */
  header_value?: string;
  location?: { latitude: number; longitude: number; name?: string; address?: string } | null;
  /** One slot per button; only the dynamic ones are read. */
  button_values?: string[];
};

export type PortalReport = {
  started: number;
  resolved: number;
  open_now: number;
  inbound_messages: number;
  human_replies: number;
  ai_replies: number;
  active_contacts: number;
  agents_online: number;
  handoffs: number;
  ai_resolved: number;
  avg_first_reply_seconds: number | null;
  avg_resolution_seconds: number | null;
  by_day: { date: string; started: number; resolved: number; inbound: number; ai_replies: number; human_replies: number }[];
  by_channel: { channel: string; started: number }[];
  by_agent: { name: string; availability: string; replies: number; assigned: number; open_now: number }[];
};

export type CannedResponse = {
  id: string;
  shortcut: string;
  content: string;
  updated_at: string;
};

export type PortalChannel = {
  channel: "whatsapp" | "whatsapp_cloud" | SocialProvider;
  id?: string;
  label?: string | null;
  provider?: SocialProvider;
  external_account_id?: string | null;
  username?: string | null;
  capabilities?: ChannelCapabilities;
  status: string;
  phone_number: string | null;
  display_name: string | null;
  supports_templates: boolean;
};

export type ContactTag = {
  id: string;
  name: string;
  color: string;
  contact_count: number;
  route_team_id?: string | null;
  route_team_name?: string | null;
  route_assignee_id?: string | null;
  route_assignee_name?: string | null;
};

export type Contact = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string;
  tags?: ContactTag[];
  created_at: string;
  updated_at: string;
  conversation_count: number;
  open_count: number;
  last_activity_at: string | null;
  blocked_at?: string | null;
};

export type ContactImportError = {
  row: number;
  name: string;
  phone: string;
  reason: string;
};

export type ContactImportResult = {
  created: number;
  updated: number;
  unchanged: number;
  errors: ContactImportError[];
  truncated: number;
};

export type PortalPublic = {
  client_name: string;
  portal_title: string;
  portal_slug: string;
  agency_name: string;
  agency_brand_color: string;
  agency_logo_url: string | null;
  client_logo_url: string | null;
};

export type SocialProvider = "instagram" | "messenger";
export type ChannelCapabilities = {
  text?: boolean;
  image?: boolean;
  video?: boolean;
  file?: boolean;
  audio?: boolean;
  reactions?: boolean;
  quotes?: boolean;
  templates?: boolean;
};
export type SocialConfig = Record<SocialProvider, {
  oauth_ready: boolean;
  manual_available: boolean;
  source: "operator" | "managed";
  webhook_url: string;
}>;
export type SocialChannel = {
  id: string;
  client_id: string;
  agent_id: string;
  provider: SocialProvider;
  external_account_id: string | null;
  display_name: string | null;
  username: string | null;
  label: string | null;
  status: string;
  is_enabled: boolean;
  has_access_token: boolean;
  has_app_secret: boolean;
  webhook_url: string;
  webhook_verify_token: string | null;
  token_expires_at: string | null;
  last_error: string | null;
  human_agent_enabled: boolean;
  connection_source: "manual" | "oauth" | "managed";
  app_id?: string | null;
  granted_scopes: string[];
  created_at: string;
  updated_at: string;
};
export type SocialPending = { setup_id: string; accounts: { id: string; name: string; username?: string | null }[] };

export type SocialHistoryJob = {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  conversations_count: number;
  messages_count: number;
  max_conversations: number;
  last_error: string | null;
  limited: boolean;
  created_at: string;
  updated_at: string;
};

export type ReportGroup = { id: string | null; name: string; replies: number; input_tokens: number; output_tokens: number; cost_usd: number };

export type OpsMetrics = {
  conversations: number; contacts: number; new_contacts: number;
  ai_resolved: number; ai_resolved_pct: number; handoffs: number; open: number; unanswered: number;
  first_reply_s: number | null; resolution_s: number | null; human_wait_s: number | null;
  inbound: number; ai_replies: number; human_replies: number; delivery_failures: number; tool_errors: number;
};
export type OpsGroup = OpsMetrics & { id: string | null; name: string };
export type OpsPeriod = { day: string; conversations: number; handoffs: number; inbound: number; outbound: number };
export type Operations = { tz: string; bucket: string; totals: OpsMetrics; by_client: OpsGroup[]; by_channel: OpsGroup[]; by_period: OpsPeriod[] };
export type ReportFilters = { clients: { id: string; name: string }[]; agents: { id: string; name: string; client_id: string }[]; channels: string[]; models: string[] };

export type CostReport = {
  totals: { cost_usd: number; replies: number; conversations: number; input_tokens: number; output_tokens: number; avg_cost_per_reply_usd: number };
  by_client: ReportGroup[];
  by_agent: ReportGroup[];
  by_model: ReportGroup[];
  by_day: { date: string; replies: number; cost_usd: number }[];
  tz: string;
};

export type ReportReply = {
  id: string;
  created_at: string;
  conversation_id: string | null;
  contact_name: string | null;
  client_id: string | null;
  client_name: string | null;
  agent_id: string | null;
  agent_name: string | null;
  channel: string | null;
  model: string;
  served_by: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  cost_usd: number;
  estimated: boolean;
  duration_ms: number | null;
  tools: number;
  tool_errors: number;
};
