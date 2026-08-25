// UI strings for the "home" area. Fill `en` and mirror it in `es`.
const en = {
  head: {
    eyebrow: "Agency overview",
    title: "Hello 👋",
    description: "Everything happening with your clients and agents, in one place.",
  },
  nextSteps: {
    title: "First steps",
    subtitle: "Get your workspace ready to start chatting",
    step1Title: "Create a client",
    step1Desc: "Add their business context.",
    step2Title: "Set up an agent",
    step2Desc: "Define instructions and personality.",
    step3Title: "Connect your model",
    step3Desc: "Use your own API key.",
  },
  metrics: {
    clients: "Clients",
    clientsActive: "{count} active",
    agents: "Agents",
    agentsActive: "{count} active",
    conversations: "Conversations",
    conversationsCaption: "saved histories",
    channels: "Channels",
    channelsConnected: "{count} connected",
  },
  range: { days: "Last {count} days" },
  activity: {
    title: "Activity",
    subtitle: "New conversations · last {count} days",
    messages: "Messages",
    humanHandled: "Handled by a person",
    empty: "No activity in this period yet.",
  },
  topAgents: {
    title: "Top agents",
    subtitle: "By conversations",
    conversations: "{count} conv.",
    empty: "No conversations yet.",
  },
  usage: {
    title: "Token usage",
    subtitle: "By model",
    in: "in",
    out: "out",
    empty: "No usage recorded yet.",
  },
  recentAgents: {
    title: "Recent agents",
    subtitle: "Your team's latest setups",
    viewAll: "View all",
    emptyTitle: "No agents yet",
    emptyDesc: "Add them from each client's workspace.",
  },
};

const es: typeof en = {
  head: {
    eyebrow: "Resumen de agencia",
    title: "Hola 👋",
    description: "Todo lo que ocurre con tus clientes y agentes, en un solo lugar.",
  },
  nextSteps: {
    title: "Primeros pasos",
    subtitle: "Deja tu espacio listo para conversar",
    step1Title: "Crea un cliente",
    step1Desc: "Añade su contexto de negocio.",
    step2Title: "Configura un agente",
    step2Desc: "Define instrucciones y personalidad.",
    step3Title: "Conecta tu modelo",
    step3Desc: "Usa tu propia API key.",
  },
  metrics: {
    clients: "Clientes",
    clientsActive: "{count} activos",
    agents: "Agentes",
    agentsActive: "{count} activos",
    conversations: "Conversaciones",
    conversationsCaption: "historiales guardados",
    channels: "Canales",
    channelsConnected: "{count} conectados",
  },
  range: { days: "Últimos {count} días" },
  activity: {
    title: "Actividad",
    subtitle: "Conversaciones nuevas · últimos {count} días",
    messages: "Mensajes",
    humanHandled: "Atendidas por una persona",
    empty: "Aún no hay actividad en este periodo.",
  },
  topAgents: {
    title: "Top agentes",
    subtitle: "Por conversaciones",
    conversations: "{count} conv.",
    empty: "Aún no hay conversaciones.",
  },
  usage: {
    title: "Uso de tokens",
    subtitle: "Por modelo",
    in: "entrada",
    out: "salida",
    empty: "Aún no hay uso registrado.",
  },
  recentAgents: {
    title: "Agentes recientes",
    subtitle: "Últimas configuraciones de tu equipo",
    viewAll: "Ver todos",
    emptyTitle: "Aún no hay agentes",
    emptyDesc: "Añádelos desde el espacio de cada cliente.",
  },
};

export const home = { en, es };
