// UI strings for the "playground" area. Fill `en` and mirror it in `es`.
const en = {
  page: {
    eyebrow: "Lab",
    title: "Playground",
    description: "Chat with your agents and validate their responses before publishing them.",
  },
  selectors: {
    client: "Client",
    agent: "Agent",
    agentPlaceholder: "Select an agent",
  },
  conversations: {
    heading: "Conversations",
    new: "New conversation",
    empty: "No conversations yet.",
  },
  chat: {
    modelConfigured: "Model configured",
    noModelConfigured: "No model configured",
    fallbackTitle: "Playground",
    fallbackSubtitle: "Select an agent to get started",
    modeHuman: "Human takeover",
    modeAi: "AI agent",
  },
  empty: {
    title: "Select an agent",
    description: "Choose a client and an agent to see their conversations.",
  },
  welcome: {
    title: "Test {name}",
    description: "Ask a question to check its instructions, tone and knowledge.",
    noModelAlert:
      "This agent does not have a model configured yet. Assign a connection in its details before sending messages.",
  },
  notReady: {
    keyPrefix: "This agent can't reply yet because it is missing your API key. Add it in ",
    settingsLink: "Settings",
    modelPrefix: "This agent can't reply yet because it has no model. Choose one in ",
    modelLink: "the agent's setup",
  },
  message: {
    you: "You",
    sourcesUsed: "Sources used",
  },
  composer: {
    placeholder: "Write a message…",
    placeholderNoAgent: "Select an agent",
    send: "Send",
    attachImage: "Attach an image",
    disclaimer: "Responses come from the configured provider and may contain errors.",
  },
};

const es: typeof en = {
  page: {
    eyebrow: "Laboratorio",
    title: "Playground",
    description: "Conversa con tus agentes y valida sus respuestas antes de publicarlos.",
  },
  selectors: {
    client: "Cliente",
    agent: "Agente",
    agentPlaceholder: "Selecciona un agente",
  },
  conversations: {
    heading: "Conversaciones",
    new: "Nueva conversación",
    empty: "No hay conversaciones todavía.",
  },
  chat: {
    modelConfigured: "Modelo configurado",
    noModelConfigured: "Sin modelo configurado",
    fallbackTitle: "Playground",
    fallbackSubtitle: "Selecciona un agente para empezar",
    modeHuman: "Atención humana",
    modeAi: "Agente IA",
  },
  empty: {
    title: "Selecciona un agente",
    description: "Elige un cliente y un agente para ver sus conversaciones.",
  },
  welcome: {
    title: "Prueba a {name}",
    description: "Haz una pregunta para comprobar sus instrucciones, tono y conocimiento.",
    noModelAlert:
      "Este agente todavía no tiene un modelo configurado. Asígnale una conexión en sus detalles antes de enviar mensajes.",
  },
  notReady: {
    keyPrefix: "Este agente todavía no puede responder porque le falta tu API key. Agrégala en ",
    settingsLink: "Configuración",
    modelPrefix: "Este agente todavía no puede responder porque no tiene modelo. Elige uno en ",
    modelLink: "la configuración del agente",
  },
  message: {
    you: "Tú",
    sourcesUsed: "Fuentes utilizadas",
  },
  composer: {
    placeholder: "Escribe un mensaje…",
    placeholderNoAgent: "Selecciona un agente",
    send: "Enviar",
    attachImage: "Adjuntar una imagen",
    disclaimer: "Las respuestas provienen del proveedor configurado y pueden contener errores.",
  },
};

export const playground = { en, es };
