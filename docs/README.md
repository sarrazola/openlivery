# OpenLivery documentation

Every guide lives here, in the repository, so a change to the product and the
change to its documentation travel in the same pull request. Guides are written
in English and Spanish; code, identifiers and commands stay English in both.

Adding a guide: write `en/<slug>.md` and `es/<slug>.md`, then list it below.

## English

Everything you need to build, brand and operate AI agents for your clients.

**Getting started**

- [Getting started](en/getting-started.md) — Run the full stack with Docker and create your first agency in minutes.
- [Configuration](en/configuration.md) — Environment variables, secrets, ports and gateway settings.

**Concepts**

- [Architecture](en/architecture.md) — The three services, the data model and how tenant isolation works.

**Agents**

- [Agents](en/agents.md) — Instructions, context, models and multimodal capabilities.
- [Knowledge base](en/knowledge-base.md) — Manual context, Q&A pairs, PDFs and semantic retrieval.
- [AI providers](en/ai-providers.md) — Connect OpenAI and Anthropic keys and pick per-agent models.
- [Custom tools](en/custom-tools.md) — Let agents call HTTP endpoints and MCP servers during a conversation.

**Channels**

- [WhatsApp](en/whatsapp.md) — Link a number per client through the Baileys bridge and hand off to a human.
- [WhatsApp Cloud API](en/whatsapp-cloud-api.md) — Connect a number through Meta's official Cloud API: app, token, webhook and going live.
- [Web chat widget](en/web-widget.md) — Embed an agent on any website with a single snippet.

**Operating**

- [Inbox](en/inbox.md) — Search, filter and take over conversations from AI to human.
- [Client portal & domains](en/client-portal.md) — Give each client a branded portal on its own custom domain.
- [Dashboard](en/dashboard.md) — Activity, top agents and token usage by model.
- [Push notifications](en/push-notifications.md) — The provider seam for mobile push: what ships, what it costs and how to register one.

**Self-hosting**

- [Self-hosting](en/self-hosting.md) — Deploy to a server, back up data, upgrade and troubleshoot.
- [Contributing](en/contributing.md) — Run the project locally, the test suites and the conventions.

## Español

Todo lo que necesitas para construir, marcar y operar agentes de IA para tus clientes.

**Primeros pasos**

- [Primeros pasos](es/getting-started.md) — Levanta el stack completo con Docker y crea tu primera agencia en minutos.
- [Configuración](es/configuration.md) — Variables de entorno, secretos, puertos y ajustes del gateway.

**Conceptos**

- [Arquitectura](es/architecture.md) — Los tres servicios, el modelo de datos y cómo funciona el aislamiento por tenant.

**Agentes**

- [Agentes](es/agents.md) — Instrucciones, contexto, modelos y capacidades multimodales.
- [Base de conocimiento](es/knowledge-base.md) — Contexto manual, pares de preguntas y respuestas, PDFs y recuperación semántica.
- [Proveedores de IA](es/ai-providers.md) — Conecta claves de OpenAI y Anthropic y elige modelos por agente.
- [Herramientas personalizadas](es/custom-tools.md) — Permite que los agentes llamen endpoints HTTP y servidores MCP durante una conversación.

**Canales**

- [WhatsApp](es/whatsapp.md) — Vincula un número por cliente con el puente de Baileys y pasa a control humano.
- [API de WhatsApp Cloud](es/whatsapp-cloud-api.md) — Conecta un número por la API Cloud oficial de Meta: app, token, webhook y salida a producción.
- [Widget de chat web](es/web-widget.md) — Integra un agente en cualquier sitio web con un único snippet.

**Operación**

- [Bandeja de entrada](es/inbox.md) — Busca, filtra y toma el control de conversaciones de IA a humano.
- [Portal del cliente y dominios](es/client-portal.md) — Dale a cada cliente un portal con su marca en su propio dominio.
- [Panel](es/dashboard.md) — Actividad, agentes destacados y uso de tokens por modelo.
- [Notificaciones push](es/push-notifications.md) — La costura de proveedores para push móvil: qué trae, qué cuesta y cómo registrar uno.

**Autoalojamiento**

- [Autoalojamiento](es/self-hosting.md) — Despliega en un servidor, respalda datos, actualiza y resuelve problemas.
- [Contribuir](es/contributing.md) — Ejecuta el proyecto en local, las suites de pruebas y las convenciones.
