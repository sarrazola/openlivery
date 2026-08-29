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
