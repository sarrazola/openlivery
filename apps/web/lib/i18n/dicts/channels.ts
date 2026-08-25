// UI strings for the "channels" area. Fill `en` and mirror it in `es`.
const en = {
  head: {
    eyebrow: "Channels",
    title: "Channels",
    description: "Connect each client's number to its own agent and Inbox. Every connection belongs to a single client: its number, agent, session and conversations stay separate from other spaces.",
  },
  toolbar: {
    clientLabel: "Client",
    allClients: "All clients",
    openClient: "Open client",
  },
  whatsappCloud: {
    status: "Available",
    title: "WhatsApp API",
    description:
      "Official WhatsApp Business Cloud API, hosted by Meta. Connect a number with your own Meta app credentials.",
    ownerPlaceholder: "Choose a client to configure its number",
    configure: "Configure WhatsApp API",
    selectClient: "Select a client",
  },
  whatsapp: {
    status: "Great for testing",
    title: "WhatsApp QR",
    description:
      "Scan a QR with the WhatsApp app on your phone and reply with an agent in minutes. Free and instant to set up, so it is ideal for demos and testing. For production, use WhatsApp API instead.",
    ownerPlaceholder: "Choose a client to configure its number",
    configure: "Configure WhatsApp QR",
    selectClient: "Select a client",
  },
  webchat: {
    status: "Available",
    title: "Webchat",
    description:
      "Embed an assistant on any website with a single line of code. Its conversations land in the same Inbox as WhatsApp.",
    ownerPlaceholder: "Choose a client to configure its widget",
    configure: "Configure widget",
    selectClient: "Select a client",
    needsAgent: "Create an agent first",
  },
  future: {
    comingSoon: "Coming soon",
    ownerPlaceholder: "Configurable inside each client",
    connect: "Connect channel",
    instagram: {
      name: "Instagram",
      description: "Reply to direct messages with the knowledge of your agents.",
    },
    facebook: {
      name: "Facebook Messenger",
      description: "Connect your pages and keep consistent support.",
    },
  },
};

const es: typeof en = {
  head: {
    eyebrow: "Canales",
    title: "Canales",
    description: "Conecta el número de cada cliente con su propio agente e Inbox. Cada conexión pertenece a un solo cliente: su número, agente, sesión y conversaciones permanecen separados de los demás espacios.",
  },
  toolbar: {
    clientLabel: "Cliente",
    allClients: "Todos los clientes",
    openClient: "Abrir cliente",
  },
  whatsappCloud: {
    status: "Disponible",
    title: "WhatsApp API",
    description:
      "API oficial de WhatsApp Business Cloud, alojada por Meta. Conecta un número con las credenciales de tu propia app de Meta.",
    ownerPlaceholder: "Elige un cliente para configurar su número",
    configure: "Configurar WhatsApp API",
    selectClient: "Selecciona un cliente",
  },
  whatsapp: {
    status: "Ideal para pruebas",
    title: "WhatsApp QR",
    description:
      "Escanea un QR con la app de WhatsApp de tu teléfono y responde con un agente en minutos. Es gratis e instantáneo de configurar, así que es ideal para demos y pruebas. Para producción usa mejor WhatsApp API.",
    ownerPlaceholder: "Elige un cliente para configurar su número",
    configure: "Configurar WhatsApp QR",
    selectClient: "Selecciona un cliente",
  },
  webchat: {
    status: "Disponible",
    title: "Webchat",
    description:
      "Inserta un asistente en cualquier sitio web con una línea de código. Sus conversaciones llegan al mismo Inbox que WhatsApp.",
    ownerPlaceholder: "Elige un cliente para configurar su widget",
    configure: "Configurar widget",
    selectClient: "Selecciona un cliente",
    needsAgent: "Crea un agente primero",
  },
  future: {
    comingSoon: "Próximamente",
    ownerPlaceholder: "Configurable dentro de cada cliente",
    connect: "Conectar canal",
    instagram: {
      name: "Instagram",
      description: "Responde mensajes directos con el conocimiento de tus agentes.",
    },
    facebook: {
      name: "Facebook Messenger",
      description: "Conecta tus páginas y mantén una atención consistente.",
    },
  },
};

export const channels = { en, es };
