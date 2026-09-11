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

export type PortalUser = {
  id: string;
  name: string;
  email: string;
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
  timezone: string;
  prompt_language: "en" | "es";
  temperature: number;
  max_tokens: number;
  memory_limit: number;
  reply_delay_min_seconds: number;
  reply_delay_max_seconds: number;
  image_enabled: boolean;
  image_model: string;
  audio_enabled: boolean;
  audio_model: string;
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
};

export type QAPair = { id: string; question: string; answer: string };

export type ToolParam = { name: string; type: "string" | "number" | "integer" | "boolean"; description: string; required: boolean };
export type McpCachedTool = { name: string; description: string; input_schema?: Record<string, unknown> };
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
  has_headers: boolean;
  created_at: string;
  updated_at: string;
};
export type ToolCallMeta = { name: string; arguments: Record<string, unknown>; result_preview: string; is_error: boolean };

export type Source = { id: string; filename: string; excerpt: string };
export type Attachment = { id: string; kind: "image" | "audio" | "video" | "file"; mime: string; filename: string | null; size_bytes: number };
export type Message = { id: string; role: "user" | "assistant" | "system"; kind?: "message" | "activity"; delivery_status?: "pending" | "sent" | "delivered" | "read" | "failed" | "unknown" | null; delivery_error?: string | null; activity?: { event: string; hours?: number | string; assignee?: string; from?: string; team?: string; target?: string; reason?: string } | null; content: string; sources: Source[]; tool_calls?: ToolCallMeta[] | null; sender_type: "visitor" | "ai" | "human"; sender_name: string | null; reaction?: string | null; incoming_reaction?: string | null; quoted_message_id?: string | null; created_at: string; attachments?: Attachment[] };

export type ConversationInbox = {
  id: string;
  agent_id: string;
  agent_name: string;
  client_id: string;
  title: string;
  contact_name: string | null;
  channel: string;
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
  channel_capabilities?: ChannelCapabilities;
  channel: string;
  external_chat_id: string | null;
  contact_name: string | null;
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
  phone_number_id: string;
  waba_id: string | null;
  coexistence: boolean;
  coexistence_sync: {
    started_at?: string;
    offboarded_at?: string;
    contacts?: { status: string; request_id?: string; error?: string };
    media?: { status: string; error?: string };
    history?: { status: string; progress?: number; request_id?: string; error?: string };
  };
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

export type Template = {
  id: string | null;
  name: string;
  language: string;
  category: string;
  status: "APPROVED" | "PENDING" | "REJECTED" | string;
  body: string;
  footer: string;
  variables: number;
  rejected_reason: string | null;
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
  avg_first_reply_seconds: number | null;
  avg_resolution_seconds: number | null;
  by_day: { date: string; started: number; resolved: number }[];
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
  provider?: SocialProvider;
  external_account_id?: string | null;
  username?: string | null;
  capabilities?: ChannelCapabilities;
  status: string;
  phone_number: string | null;
  display_name: string | null;
  supports_templates: boolean;
};

export type Contact = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string;
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
