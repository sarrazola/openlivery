# Portal del cliente y dominios

> Read in English: [client-portal.md](../en/client-portal.md)

Cada cliente tiene su propio portal: un inicio de sesión independiente y una bandeja de entrada enfocada donde puede leer conversaciones y tomar el control de la IA, sin ver nunca el panel de tu agencia. Opcionalmente, puedes servir ese portal en el dominio propio del cliente con HTTPS automático.

## El portal del cliente

El portal es un espacio autocontenido acotado a un único cliente. Tiene su propio inicio de sesión (separado de tu cuenta de agencia) y muestra solo los agentes y conversaciones de ese cliente — la misma bandeja de entrada que usan tus operadores, pero limitada a un cliente. Desde ahí, el cliente puede cambiar una conversación a modo `human` para pausar la IA y responder él mismo.

El portal está desactivado por defecto. Lo activas por cliente desde la configuración del cliente, y solo queda accesible una vez que se han definido un correo y una contraseña de acceso.

## Configuración del portal

En un cliente configuras estos campos:

- **`portal_enabled`** — el interruptor que activa el portal. No se puede activar hasta que haya un `portal_email` y una contraseña.
- **`portal_slug`** — el segmento de URL del portal (p. ej. `acme` → `/portal/acme`). Se genera a partir del nombre del cliente al crearlo, debe ser único y se normaliza a slug cuando lo cambias.
- **`portal_title`** — el encabezado que se muestra en el inicio de sesión y la bandeja del portal. Si se deja vacío, usa `"<Nombre del cliente> Inbox"`.
- **`portal_email`** — la dirección con la que inicia sesión el cliente.
- **`portal_password`** — la contraseña del cliente (mínimo 8 caracteres). Se almacena con hash; la API solo informa si hay una configurada, nunca su valor.

Activar el portal sin correo y contraseña se rechaza.

## Personas y roles

Las personas que entran a un portal las gestiona la agencia desde la pestaña **Portal** del cliente (`/api/clients/{id}/portal-users`). Cada persona tiene un rol:

- **Administrador** puede hacer todo en el portal.
- **Agente** trabaja la bandeja: lee y responde, toma una conversación de la IA y se la devuelve, cambia su estado, la asigna a una persona o a un equipo, crea contactos y les pone etiquetas existentes, y cambia su propia disponibilidad. Un agente no puede borrar ni archivar conversaciones, importar, exportar, borrar, fusionar ni bloquear contactos, gestionar etiquetas, plantillas de WhatsApp, respuestas guardadas ni equipos, ni abrir los reportes.

La primera persona que se agrega a un negocio es su administrador; las siguientes empiezan como agentes hasta que la agencia lo cambie. La API protege cada ruta por clave de permiso (`app/portal_permissions.py`), así que la app móvil queda cubierta por la misma regla, y la sesión del portal (`GET /api/portal/{slug}/me`) lista los permisos de la persona para que la interfaz oculte lo que no puede hacer.

## Equipos y plantillas desde la agencia

Los equipos y las plantillas de WhatsApp son del cliente y se pueden gestionar desde los dos lados: el portal del cliente, o la página del cliente en la agencia bajo sus pestañas **Equipos** y **Plantillas de WhatsApp** (`/api/clients/{id}/teams`, `/api/clients/{id}/templates`). Las dos puertas editan las mismas filas.

## URL del portal

Cada portal activado se sirve en:

```
/portal/<slug>
```

Por ejemplo, un cliente con slug `acme` en un stack en `https://app.example.com` accede a su portal en `https://app.example.com/portal/acme`. El inicio de sesión, la bandeja de entrada y las vistas de conversación del portal viven bajo esta ruta.

## Dominio propio por cliente (opcional)

En lugar de la ruta compartida `/portal/<slug>`, puedes apuntar el portal a un dominio que el cliente posea, como `support.acme.com`, con un certificado emitido automáticamente.

### Añadir un dominio propio

1. En la configuración del cliente, define el dominio propio (p. ej. `support.acme.com`). Al guardarlo se reinicia la verificación y se emite un token de desafío nuevo.
2. Crea un registro DNS **TXT** en `_openlivery-challenge.<domain>` con el valor del token que aparece en la configuración.
3. Haz clic en **Verificar**. OpenLivery resuelve el registro TXT; en cuanto coincide con el token, el dominio se marca como verificado.
4. Apunta el dominio a tu servidor (un registro A/AAAA o CNAME para `support.acme.com`).
5. Asegúrate de que la pasarela de TLS bajo demanda esté habilitada (ver más abajo) — el certificado se obtiene automáticamente en la primera petición.

### Cómo funciona

- El endpoint público y no autenticado `GET /api/public/portal-domain?domain=<host>` mapea un host a su portal. Devuelve `{ "portal_slug": ... }` solo cuando el dominio coincide con un cliente verificado y activado, y un código no-2xx en caso contrario.
- El `proxy.ts` de Next.js resuelve el host entrante contra ese endpoint y reescribe un host verificado a `/portal/<slug>`, de modo que la URL del navegador permanece en el dominio propio del cliente. Alcanza la API en el lado del servidor mediante `BACKEND_INTERNAL_URL` — ver [Configuración](configuration.md).
- `docker/Caddyfile.ondemand` restringe el TLS bajo demanda con el mismo endpoint como su hook `ask`, así que solo se emite un certificado para dominios de portal verificados y nunca para hosts arbitrarios apuntados al servidor.

La pasarela bajo demanda es opcional. Consulta [Self-hosting](self-hosting.md) para montar el override y publicar los puertos 80 y 443.

## Archivar y eliminar conversaciones

Las conversaciones son el historial del cliente, así que nada las quita en un solo paso.

- **Archivar** una conversación resuelta desde su cabecera, o todas las resueltas de una vez desde la bandeja Resueltas. Las archivadas salen de las bandejas, conservan todos sus mensajes, siguen contando en los reportes y se pueden restaurar (vuelven como resueltas). Archivar una conversación abierta la resuelve primero.
- **Eliminar** solo desde la bandeja Archivadas, una por una o todas, después de escribir la palabra de confirmación. Eliminar borra la conversación y sus mensajes de la base de datos de forma definitiva.

Eliminar un agente desde el panel nunca toca las conversaciones: se quedan en el portal con el nombre del agente. Eliminar un cliente sí las borra, junto con todo lo demás que hay bajo el cliente.

API: `GET /api/portal/{slug}/conversations?archived=1`, `PATCH .../conversations/{id}/archive` con `{"archived": true|false}`, `POST .../conversations/archive-resolved`, `DELETE .../conversations/{id}` (solo archivadas), `POST .../conversations/delete-archived`. El resumen de la bandeja trae un conteo `archived`.

## Bloquear un contacto

Un contacto que hace spam al número se puede **bloquear** desde Contactos o desde la cabecera de la conversación. Bloqueado, sus mensajes se siguen guardando pero nadie los responde: el agente no contesta ni gasta tokens, no suena ninguna notificación y sus conversaciones salen de todas las bandejas (siguen legibles desde el historial del contacto). Puede seguir escribiendo; solo que no recibe respuesta.

**Desbloquear** no responde lo acumulado. La conversación abierta se resuelve con una nota en el hilo, y el siguiente mensaje del contacto abre una conversación nueva que el agente atiende normal.

API: `POST /api/portal/{slug}/contacts/{id}/block` con `{"blocked": true|false}`; `ContactOut.blocked_at` indica si está bloqueado. Es un bloqueo interno: a WhatsApp no se le avisa, así que el contacto ve sus mensajes como entregados.
