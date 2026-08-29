# Configuración

> Read in English: [configuration.md](../en/configuration.md)

OpenLivery se configura mediante variables de entorno. En Docker, todas viven en un único archivo `.env.docker` en la raíz del repositorio; un script auxiliar lo genera con secretos aleatorios robustos para que nunca tengas que inventarlos.

## El archivo .env.docker

Ejecuta el generador una vez por clon:

```bash
./scripts/generate-docker-env.sh   # crea .env.docker y se niega a sobrescribir uno existente
```

Crea el archivo con permisos restrictivos (`umask 077`) y rellena los valores sensibles con `openssl rand`: una contraseña de Postgres, `SECRET_KEY`, `ENCRYPTION_KEY` y `WHATSAPP_BRIDGE_TOKEN`. Compose lee este archivo (`docker compose --env-file .env.docker`, que `make` hace por ti). El archivo está en gitignore: mantenlo fuera del control de versiones y guárdalo en un lugar seguro.

Para una instalación local sin Docker, las mismas variables van en un `.env` en la raíz del repositorio o en `apps/api/.env`; consulta `.env.example`.

## Variables principales

| Variable | Propósito | Valor por defecto |
| --- | --- | --- |
| `DATABASE_URL` | Cadena de conexión de SQLAlchemy. En Docker se arma a partir de `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` apuntando al servicio `db` | Postgres local |
| `SECRET_KEY` | Firma los tokens de sesión JWT. Rotarla cierra la sesión de todos | placeholder de desarrollo |
| `ENCRYPTION_KEY` | Cifra las claves de API de IA y el estado de sesión de WhatsApp antes de guardarlos en la base de datos | placeholder de desarrollo |
| `ACCESS_TOKEN_MINUTES` | Duración de la sesión | `10080` (7 días) |
| `COOKIE_SECURE` | Enviar la cookie de sesión solo por HTTPS. Ponla en `true` en producción | `false` |
| `COOKIE_SAMESITE` | Política SameSite de la cookie. Usa `none` cuando el frontend y la API están en sitios distintos (requiere `COOKIE_SECURE=true`) | `lax` |
| `RATE_LIMIT_ENABLED` | Límite de peticiones por IP en endpoints públicos (auth, login del portal, widget) | `true` |
| `FRONTEND_URL` | Origen permitido por CORS | `http://localhost:3000` |
| `WHATSAPP_BRIDGE_TOKEN` | Secreto compartido que autentica las llamadas entre backend ↔ puente de WhatsApp. Usa el mismo valor en ambos | aleatorio |
| `NEXT_PUBLIC_API_URL` | Origen público de la API incrustado en el frontend en tiempo de compilación. Déjalo vacío para usar el mismo origen a través del gateway | vacío |
| `BACKEND_INTERNAL_URL` | Cómo alcanza el contenedor web a la API desde el servidor (usado por `proxy.ts` para dominios de portal personalizados) | `http://api:8000` |

### La advertencia sobre ENCRYPTION_KEY

`ENCRYPTION_KEY` **nunca** debe cambiar una vez que se han almacenado secretos. Deriva la clave que descifra cada clave de API de IA guardada y cada sesión de WhatsApp. Si la rotas o la pierdes, esos secretos quedan irrecuperables: tendrás que volver a introducir las claves de API y a vincular los números de WhatsApp. Trátala como permanente durante toda la vida de tu base de datos.

## Puertos del host

Compose enlaza cada servicio a un puerto del host, todos sobrescribibles. Pásalos en línea a `make up`:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

| Variable | Qué controla | Valor por defecto |
| --- | --- | --- |
| `WEB_PORT` | El puerto del gateway: esta es la app | `3000` |
| `API_PORT` | Backend, expuesto localmente para la documentación OpenAPI y herramientas | `8000` |
| `DB_PORT` | PostgreSQL | `5432` |
| `BIND_HOST` | Interfaz a la que enlazar: `127.0.0.1` solo local, `0.0.0.0` para exponer en un servidor | `127.0.0.1` |

El puente de WhatsApp escucha en `3101` pero no se publica al host en Docker.

## El gateway de origen único

Un contenedor Caddy (`docker/Caddyfile`) sirve toda la pila en un único origen. Enruta `/api/*` al backend y todo lo demás al frontend, de modo que el navegador habla con un solo puerto y `NEXT_PUBLIC_API_URL` puede quedar vacío. La pila sirve solo HTTP plano: coloca tu propio reverse proxy delante del gateway para TLS en producción. Consulta [Autoalojamiento](self-hosting.md) para un despliegue público.
