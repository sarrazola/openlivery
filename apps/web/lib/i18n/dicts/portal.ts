// UI strings for the "portal" area. Fill `en` and mirror it in `es`.
const en = {
  loader: {
    loading: "Loading portal…",
    unavailable: "Portal not available",
  },
  access: {
    secureBadge: "Secure client portal",
    eyebrow: "Client portal",
    intro:
      "Review the conversations, follow along with the agent, and take control whenever a person needs to step in.",
    preview: {
      inbox: "Inbox",
      conversationsCount: "8 conversations",
      newInquiry: "New inquiry",
      newInquiryMeta: "AI agent · Now",
      salesFollowUp: "Sales follow-up",
      salesFollowUpMeta: "Human support · 12 min",
      servicesInfo: "Services information",
      servicesInfoMeta: "AI agent · 34 min",
      agentReplying: "Agent replying",
      takeControl: "Take control",
    },
    form: {
      cardLabel: "Client access",
      welcome: "Welcome to {name}",
      subtitle: "Use the credentials your agency provided.",
      emailLabel: "Email address",
      emailPlaceholder: "team@company.com",
      passwordLabel: "Password",
      passwordPlaceholder: "Your password",
      submit: "Enter the Inbox",
      security: "Private access managed by {name}.",
    },
  },
  inbox: {
    nav: {
      inbox: "Inbox",
      agents: "Agents",
      logout: "Log out",
    },
    header: {
      eyebrow: "Client portal",
      conversationsCount: "{count} conversations",
    },
    list: {
      humanSupport: "Human support",
      aiAgent: "AI agent",
      noMessages: "No messages yet",
    },
    status: {
      open: "Open",
      resolved: "Resolved",
    },
    conversation: {
      channel: "Channel: {channel}",
      takeControl: "Take control",
      returnToAi: "Return to AI",
      resolve: "Resolve",
      reopen: "Reopen",
      resolvedBadge: "Resolved",
      agent: "Agent",
      visitor: "Visitor",
      replyPlaceholder: "Write a reply…",
      takeControlToReply: "Take control to reply",
      reopenToReply: "Reopen the conversation to reply",
    },
    activity: {
      resolved: "{actor} resolved the conversation",
      reopened: "{actor} reopened the conversation",
      reopened_by_contact: "Reopened: the contact wrote again",
      taken_over: "{actor} took over the conversation",
      returned_to_ai: "{actor} returned the conversation to the AI",
      someone: "Someone",
    },
    empty: {
      title: "The Inbox is empty",
      description:
        "Conversations will appear here once your agents start receiving messages.",
    },
  },
};

const es: typeof en = {
  loader: {
    loading: "Cargando portal…",
    unavailable: "Portal no disponible",
  },
  access: {
    secureBadge: "Portal seguro de cliente",
    eyebrow: "Portal de cliente",
    intro:
      "Revisa las conversaciones, acompaña al agente y toma el control cuando una persona necesite intervenir.",
    preview: {
      inbox: "Inbox",
      conversationsCount: "8 conversaciones",
      newInquiry: "Nueva consulta",
      newInquiryMeta: "Agente IA · Ahora",
      salesFollowUp: "Seguimiento comercial",
      salesFollowUpMeta: "Atención humana · 12 min",
      servicesInfo: "Información de servicios",
      servicesInfoMeta: "Agente IA · 34 min",
      agentReplying: "Agente respondiendo",
      takeControl: "Tomar control",
    },
    form: {
      cardLabel: "Acceso del cliente",
      welcome: "Bienvenido a {name}",
      subtitle: "Usa las credenciales que te facilitó tu agencia.",
      emailLabel: "Correo electrónico",
      emailPlaceholder: "equipo@empresa.com",
      passwordLabel: "Contraseña",
      passwordPlaceholder: "Tu contraseña",
      submit: "Entrar al Inbox",
      security: "Acceso privado administrado por {name}.",
    },
  },
  inbox: {
    nav: {
      inbox: "Inbox",
      agents: "Agentes",
      logout: "Cerrar sesión",
    },
    header: {
      eyebrow: "Portal del cliente",
      conversationsCount: "{count} conversaciones",
    },
    list: {
      humanSupport: "Atención humana",
      aiAgent: "Agente IA",
      noMessages: "Aún sin mensajes",
    },
    status: {
      open: "Abiertas",
      resolved: "Resueltas",
    },
    conversation: {
      channel: "Canal: {channel}",
      takeControl: "Tomar control",
      returnToAi: "Devolver a IA",
      resolve: "Resolver",
      reopen: "Reabrir",
      resolvedBadge: "Resuelta",
      agent: "Agente",
      visitor: "Visitante",
      replyPlaceholder: "Escribe una respuesta…",
      takeControlToReply: "Toma el control para responder",
      reopenToReply: "Reabre la conversación para responder",
    },
    activity: {
      resolved: "{actor} resolvió la conversación",
      reopened: "{actor} reabrió la conversación",
      reopened_by_contact: "Reabierta: el contacto volvió a escribir",
      taken_over: "{actor} tomó el control de la conversación",
      returned_to_ai: "{actor} devolvió la conversación a la IA",
      someone: "Alguien",
    },
    empty: {
      title: "El Inbox está vacío",
      description:
        "Las conversaciones aparecerán aquí cuando tus agentes empiecen a recibir mensajes.",
    },
  },
};

export const portal = { en, es };
