# Arquitectura

> Read in English: [architecture.md](../en/architecture.md)

OpenLivery es una plataforma multi-tenant: tres servicios de aplicación más PostgreSQL, servidos a través de una puerta de enlace de origen único. Esta página explica cómo encajan las piezas, cómo se estructuran los datos y cómo se mantiene aislado cada tenant.

## Los servicios

El stack son cuatro contenedores orquestados por Docker Compose. Tres de ellos son código de aplicación; el cuarto es la base de datos.

| Servicio | Ruta | Stack | Rol |
| --- | --- | --- | --- |
| Backend | `apps/api/` | FastAPI (Python 3.12), SQLAlchemy, Alembic | API REST, autenticación, orquestación de IA, recuperación de conocimiento |
| Frontend | `apps/web/` | Next.js (App Router), React, TypeScript, Tailwind | Panel, playground, portal del cliente, widget web |
| Puente de WhatsApp | `apps/whatsapp/` | Node.js sobre Baileys | Mantiene las sesiones vivas de WhatsApp y retransmite mensajes |
| Base de datos | — | PostgreSQL | Fuente única de verdad para todo el estado |

## La puerta de enlace

Todo se sirve desde un único origen mediante una puerta de enlace Caddy (`docker/Caddyfile`). Enruta `/api/*` al backend y todo lo demás al frontend:

```caddyfile
:80 {
	handle /api/* {
		reverse_proxy api:8000
	}
	handle {
		reverse_proxy web:3000
	}
}
```

Como la aplicación es de origen único, el navegador habla con una ruta relativa `/api` y no se necesita CORS para el flujo normal. TLS no viene incluido: coloca tu propio proxy inverso delante del puerto de la puerta de enlace. Consulta [Autoalojamiento](self-hosting.md) para la configuración de producción.

## El modelo de datos

Cada registro cuelga de una agencia. La jerarquía, tal como se define en `apps/api/app/models.py`:

```text
Agency
├── User            (personal de la agencia, cuentas de acceso)
├── ProviderCredential  (una clave de IA cifrada por proveedor)
└── Client
    ├── Agent
    │   ├── KnowledgeDocument → KnowledgeChunk
    │   ├── AgentQA           (pares de pregunta/respuesta)
    │   └── Conversation → Message
    └── WhatsAppChannel  (uno por cliente, vinculado a un agente)
```

Una `Conversation` registra su `channel` (playground, widget o WhatsApp) y un `mode` (`ai` o `human`); cambiar a `human` pausa la IA para que un operador pueda responder desde el inbox. Los mensajes guardan su rol, contenido y las `sources` de conocimiento utilizadas. Consulta [Agentes](agents.md) para ver cómo las instrucciones, el brief y el conocimiento de un agente componen el prompt.

## Aislamiento de tenants

La agencia es la frontera del tenant. Las tablas `Agency`, `User`, `Client`, `Agent`, `WhatsAppChannel`, `Conversation` y otras llevan un `agency_id` indexado, y toda consulta autenticada de los routers filtra por el `agency_id` de quien llama. Eliminar una agencia propaga en cascada a todo lo que le pertenece. Cualquier endpoint nuevo debe preservar este filtro.

## Cifrado en reposo

Los valores sensibles nunca llegan a la base de datos en texto plano. Las claves de API de los proveedores de IA (`ProviderCredential.encrypted_api_key`) y el estado de sesión de WhatsApp (`WhatsAppChannel.encrypted_auth_state`, `encrypted_qr`) se cifran con Fernet, usando una clave derivada de `ENCRYPTION_KEY` (`apps/api/app/security.py`). Este valor nunca debe cambiar una vez que se han almacenado secretos, o dejarán de poder descifrarse. Las contraseñas se hashean con bcrypt. Consulta [Configuración](configuration.md).

## Comportamiento en tiempo de ejecución

- **Migraciones al arrancar** — el backend ejecuta `alembic upgrade head` antes de aceptar tráfico, de modo que el esquema siempre está actualizado. Los cambios de esquema requieren una nueva migración de Alembic.
- **Puente con estado** — el puente de WhatsApp (`apps/whatsapp/src/manager.ts`) mantiene en memoria los sockets vivos de Baileys y recarga al arrancar las sesiones habilitadas desde el estado cifrado en PostgreSQL. El backend y el puente se autentican entre sí con `WHATSAPP_BRIDGE_TOKEN`. Consulta [WhatsApp](whatsapp.md).
- **Límite de tasa** — los endpoints públicos y no autenticados se limitan por IP con un limitador en memoria (`apps/api/app/ratelimit.py`), usando como clave la dirección del cliente obtenida de `X-Forwarded-For`.
