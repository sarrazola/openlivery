# Autoalojar OpenLivery

> Read in English: [self-hosting.md](../en/self-hosting.md)

Levanta y opera tu propia instancia de OpenLivery. Para una vista general de las
funcionalidades, mira el [README](../../README.md).

OpenLivery se orquesta con Docker Compose, y un `Makefile` envuelve los comandos
habituales. Un **gateway** ligero (Caddy) es el único punto de entrada público:
sirve la aplicación y enruta `/api/*` al backend, así que el frontend y la API
comparten un mismo origen.

| Servicio | Imagen | Rol |
| --- | --- | --- |
| `proxy` | Caddy | Gateway HTTP, el origen único de la app (enruta `/api/*` → backend). |
| `web` | Next.js | Panel de la agencia, portal del cliente, playground y widget (interno). |
| `api` | FastAPI | API REST, modelos, servicios de IA, conocimiento y proveedores (interno). |
| `db` | PostgreSQL | Todos los datos, con los secretos cifrados en reposo (interno). |
| `whatsapp` | Go + whatsmeow | Puente con WhatsApp Web (interno). |

Solo el gateway está pensado para ser público. Para HTTPS, pon tu propio proxy
inverso delante (mira [Pasar a producción](#pasar-a-producción-https)). Una
instancia = **una agencia** (el primer usuario registrado es su administrador).

> **¿Por qué Caddy como gateway?** El enrutado es deliberadamente simple, dos
> destinos y una regla (`/api/*` → backend, todo lo demás → frontend), y la
> autenticación vive en la API (JWT en una cookie httpOnly), no en el borde. Un
> binario pequeño con una configuración mínima encaja con eso; los gateways
> programables más pesados (Envoy, Kong) se ganan su sitio con muchos servicios y
> validación de claves en el borde, que este stack no necesita. El gateway está
> aislado en el servicio `proxy`, así que cambiarlo más adelante no toca nada más.

## Contenido

- [Antes de empezar](#antes-de-empezar)
- [Instalación](#instalación)
- [Acceder a tu instalación](#acceder-a-tu-instalación)
- [Asegurar tu instalación](#asegurar-tu-instalación)
- [Pasar a producción (HTTPS)](#pasar-a-producción-https)
- [Variables de entorno](#variables-de-entorno)
- [Gestionar tu instalación](#gestionar-tu-instalación)
- [Datos persistentes](#datos-persistentes)
- [Copias de seguridad](#copias-de-seguridad)
- [Actualizar](#actualizar)
- [Desinstalar](#desinstalar)
- [Correr sin Docker](#correr-sin-docker)
- [Conectar WhatsApp](#conectar-whatsapp)
- [Tests](#tests)
- [Advertencias de WhatsApp / whatsmeow](#advertencias-de-whatsapp--whatsmeow)
- [Resolución de problemas](#resolución-de-problemas)

## Antes de empezar

Necesitas una máquina con Docker:

- macOS / Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- Linux o un servidor: Docker Engine con el plugin de Compose.

Comprueba que está corriendo:

```bash
docker --version
docker compose version
```

Para un despliegue público necesitas además un **dominio** y un servidor con los
puertos **80** y **443** abiertos (mira [Pasar a producción](#pasar-a-producción-https)).

## Instalación

```bash
git clone <REPOSITORY_URL>
cd openlivery
./scripts/generate-docker-env.sh   # writes .env.docker with random secrets (gitignored)
make up                            # build, start, run migrations
```

`make up` construye las imágenes, arranca los contenedores, crea la base de datos
y aplica las migraciones de Alembic. Todos los servicios deberían reportar
`healthy`:

```bash
make ps
```

Sobrescribe los puertos del host cuando choquen con otros servicios:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

### Arrancar desde imágenes precompiladas (sin build local)

En cada push a `main` se publican imágenes etiquetadas en el GitHub Container
Registry, así que un servidor puede saltarse el build y descargarlas:

```bash
make pull        # docker compose pull + up -d
```

Esto descarga `ghcr.io/sarrazola/openlivery-{api,web,whatsapp}:latest`. Fija una
versión con `OPENLIVERY_VERSION=v1.2.3 make pull`, o apunta a tu propio registro
con `OPENLIVERY_IMAGE_PREFIX`. La imagen `web` precompilada llama a la API a
través del gateway con un `/api` relativo; para apuntar a una API en otro origen
tienes que construir el frontend tú mismo con `NEXT_PUBLIC_API_URL` definida.

## Acceder a tu instalación

- **App y panel**: http://localhost:3000 (el gateway)
- **Documentación de la API**: http://localhost:8000/docs (la API se expone en local para herramientas)
- **PostgreSQL**: `make shell-db` (o conéctate a `localhost:5432`)

En la primera pantalla elige **Crear agencia**; esa cuenta es la administradora.
Solo el gateway está pensado para ser alcanzable públicamente; el web, la API, la
base de datos y el puente de WhatsApp se quedan en la red privada de Compose.

## Asegurar tu instalación

Haz esto antes de exponer OpenLivery a alguien más.

- **Secretos.** `generate-docker-env.sh` rellena `SECRET_KEY`, `ENCRYPTION_KEY`,
  `WHATSAPP_BRIDGE_TOKEN` y `POSTGRES_PASSWORD` con valores aleatorios. Si los
  pones a mano, usa cadenas largas y aleatorias, y nunca las reutilices entre
  instalaciones.
- ⚠️ **`ENCRYPTION_KEY` no debe cambiar nunca** una vez que hay secretos
  guardados: es la que descifra las claves de los proveedores y los marcadores
  de sesión de WhatsApp. Perderla o cambiarla los vuelve irrecuperables.
- **Mantén los servicios privados.** Deja `BIND_HOST=127.0.0.1` (el valor por
  defecto) para que la base de datos, la API y el frontend solo sean alcanzables
  desde el host; expón la aplicación a internet **únicamente** a través del proxy
  inverso (siguiente sección). Nunca publiques el puerto de PostgreSQL en una
  interfaz pública.
- **No subas `.env.docker`** al repositorio, ni ninguna copia de seguridad que lo
  contenga; guárdalo en un gestor de secretos.
- Las claves de los proveedores se cifran en reposo y nunca se devuelven enteras
  al navegador; el marcador de sesión de WhatsApp y el QR también van
  cifrados. `WHATSAPP_BRIDGE_TOKEN` autentica las llamadas privadas entre el
  backend y el puente: no lo reutilices como contraseña ni como clave.
- **Límite de peticiones.** Los endpoints públicos sin autenticar están limitados
  por IP del cliente: inicio de sesión y registro (de agencia y de portal) para
  frenar la fuerza bruta, y el endpoint de mensajes del widget web porque cada
  llamada gasta tokens del modelo. Los límites viven en memoria (suficiente para
  una instancia); pon `RATE_LIMIT_ENABLED=false` si el proxy de delante ya los
  aplica, o añade límites a nivel de proxy en un despliegue escalado. El limitador
  lee el cliente de `X-Forwarded-For`, que el gateway rellena.

## Pasar a producción (HTTPS)

El stack sirve HTTP plano en el gateway. Para un despliegue público, pon **tu
propio proxy inverso** (Caddy, nginx, Traefik, un balanceador de tu nube…)
delante del gateway para terminar TLS con tu dominio, que es el modelo habitual
de autoalojamiento.

1. Levanta el stack; el gateway escucha en `${WEB_PORT}` (por defecto `3000`),
   atado a `127.0.0.1`.
2. Apunta tu proxy inverso a `127.0.0.1:${WEB_PORT}` y sirve tu dominio por
   HTTPS. Como la app y la API comparten origen, pasa el **dominio entero** a ese
   único puerto: no hay nada más que enrutar.
3. Pon `COOKIE_SECURE=true` en `.env.docker` y reinicia, para que la cookie de
   sesión solo viaje por TLS.

Ejemplo con Caddy (HTTPS automático) corriendo en el host:

```caddyfile
agency.example.com {
	reverse_proxy 127.0.0.1:3000
}
```

Mantén privados la base de datos, la API y el puente de WhatsApp
(`BIND_HOST=127.0.0.1`, el valor por defecto); solo tu proxy inverso debería dar
la cara a internet.

## Dominios propios para los portales de cliente

Por defecto el portal de un cliente vive en `tu-dominio/portal/<slug>`. También
puedes servirlo bajo el **dominio del propio cliente** (por ejemplo
`chat.marca.com`) para una experiencia de marca blanca completa. Es opcional
porque exige que el gateway termine TLS y obtenga certificados bajo demanda.

**1. Habilita el gateway multidominio.** Crea un `docker-compose.override.yml`
junto a `docker-compose.yml` (Compose lo combina automáticamente):

```yaml
services:
  proxy:
    volumes:
      - ./docker/Caddyfile.ondemand:/etc/caddy/Caddyfile:ro
      - caddy_data:/data          # persist issued certificates across restarts
    environment:
      PRIMARY_DOMAIN: app.youragency.com   # your main domain
    ports:
      - "80:80"
      - "443:443"

volumes:
  caddy_data:
```

Apunta `app.youragency.com` (y cada dominio de cliente) a este servidor, y
después `make up`. El gateway obtiene el certificado del dominio principal de la
manera normal, y el de cada dominio de cliente **bajo demanda**, pero solo
después de preguntarle a la API si ese dominio es un dominio de portal verificado
(`/api/public/portal-domain`), así que nunca emite certificados para hosts
arbitrarios apuntados a tu IP.

**2. Añade el dominio de un cliente.** En el panel abre el cliente → pestaña
**Portal** → **Dominio propio**, escribe el dominio y guarda. Crea los dos
registros DNS que te muestra:

| Tipo | Host | Valor |
| --- | --- | --- |
| `CNAME` | `chat.marca.com` | el host de tu gateway (por ejemplo `app.youragency.com`) |
| `TXT` | `_openlivery-challenge.chat.marca.com` | el token que se muestra |

Pulsa **Verificar**. Cuando encuentre el registro TXT, el dominio queda marcado
como verificado, el gateway empieza a emitir su certificado y el frontend enruta
el dominio al portal de ese cliente. El portal tiene que estar **publicado** para
que el dominio sirva algo.

> Sin el override, la app se queda de origen único detrás de tu propio proxy
> inverso, y los portales solo son alcanzables en `/portal/<slug>`.

## Variables de entorno

`generate-docker-env.sh` rellena los secretos. Para poner los valores a mano,
copia `.env.docker.example` a `.env.docker` y reemplaza cada `CHANGE_*`.

| Variable | Ámbito | Uso |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Red privada | Base de datos PostgreSQL principal. |
| `POSTGRES_TEST_DB` | Red privada | Base de datos aislada para `pytest`. |
| `SECRET_KEY` | Backend | Firma las sesiones de agencia y de portal. |
| `ENCRYPTION_KEY` | Backend / datos persistidos | Cifra las claves de API, el QR y el marcador de sesión de WhatsApp. **No debe cambiar** una vez guardados los secretos. |
| `WHATSAPP_BRIDGE_TOKEN` | Backend y puente | Autentica las llamadas privadas entre backend y puente. |
| `WHATSAPP_STORE_URL` | Puente | Dónde guarda whatsmeow las claves de sesión: un archivo SQLite local (`file:whatsmeow.db`) por defecto, o una URL `postgres://`. Compose la apunta al PostgreSQL incluido con `?search_path=whatsmeow` para que sus tablas vivan en un esquema dedicado. |
| `FRONTEND_URL` | Backend | Origen permitido por CORS (solo hace falta si sirves la API en otro origen). |
| `NEXT_PUBLIC_API_URL` | Navegador / build del frontend | Déjala vacía (por defecto): el navegador llama a la API por el gateway con un `/api` relativo. Ponla solo para apuntar el frontend a una API en otro origen (se fija en tiempo de build). |
| `COOKIE_SECURE` | Backend | `true` detrás de HTTPS, para que la cookie de sesión solo viaje por TLS. |
| `COOKIE_SAMESITE` | Backend | `lax` (por defecto); `none` cuando frontend y API están en sitios distintos (exige `COOKIE_SECURE=true`). |
| `ACCESS_TOKEN_MINUTES` | Backend | Duración de la sesión. |
| `WHATSAPP_LOG_LEVEL` | Puente | Nivel de log; `silent` evita exponer datos sensibles. |
| `API_PORT`, `WEB_PORT`, `DB_PORT` | Host | Puertos del host (por defecto `8000` / `3000` / `5432`). |
| `BIND_HOST` | Host | Dirección de escucha: `127.0.0.1` (local) o `0.0.0.0` (exposición directa). |

## Gestionar tu instalación

```bash
make logs                 # follow logs from all services (SERVICE=api to filter)
make ps                   # service status
make stop                 # stop containers (keep them)
make start                # start stopped containers
make restart              # restart all services
make migrate              # apply Alembic migrations in the running api container
make shell-api            # shell inside the api container
make shell-db             # psql inside the database
make down                 # stop and remove containers (keeps data volumes)
```

Ejecuta `make help` para la lista completa.

## Datos persistentes

Todo el estado vive en volúmenes de Docker con nombre, así que `make down` y las
actualizaciones lo conservan:

| Volumen | Contenido |
| --- | --- |
| `postgres_data` | La base de datos PostgreSQL: agencias, agentes, conversaciones, claves de proveedores cifradas, los marcadores de sesión de WhatsApp cifrados y el almacén de sesiones de whatsmeow (su propio esquema `whatsmeow`). |
| `backend_storage` | Archivos subidos (por ejemplo los PDF de la base de conocimiento). |

`ENCRYPTION_KEY` descifra las claves de los proveedores y los marcadores de
sesión de WhatsApp. **No la cambies nunca** una vez que hay secretos guardados,
o quedan irrecuperables; trátala como parte de tu copia de seguridad.

## Copias de seguridad

Exporta PostgreSQL sin parar la aplicación:

```bash
mkdir -p backups
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/openlivery.dump
```

Guarda también `.env.docker` en un gestor de secretos: una copia con claves de
API o una sesión de WhatsApp necesita la misma `ENCRYPTION_KEY` para poder
descifrarse.

Restaurar (reemplaza los datos de la base de destino, haz copia antes):

```bash
docker compose --env-file .env.docker stop api whatsapp
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/openlivery.dump
docker compose --env-file .env.docker start api whatsapp
```

## Actualizar

```bash
git pull
make up        # rebuilds and restarts; your reverse proxy stays in front
```

Se construyen las imágenes nuevas y el backend ejecuta `alembic upgrade head` al
arrancar, así que los cambios de esquema se aplican solos. Haz una copia de
seguridad antes.

Si actualizas desde una versión cuyo puente estaba construido sobre Baileys, las
sesiones antiguas de WhatsApp no se pueden migrar: vuelve a conectar cada canal
escaneando su QR una vez más.

## Desinstalar

`make down` elimina los contenedores y la red, pero conserva tus datos. Para
borrar **todo** (base de datos, PDF, claves y sesiones de WhatsApp en los
volúmenes):

```bash
make destroy   # irreversible
```

## Correr sin Docker

Requisitos: Python 3.12+, Node.js 20+, Go 1.27+ y PostgreSQL 14+ en marcha.

```bash
# 1) databases
psql -d postgres -c "CREATE ROLE openlivery LOGIN PASSWORD 'openlivery';"
createdb -O openlivery openlivery
createdb -O openlivery openlivery_test

# 2) env
cp .env.example .env          # then set SECRET_KEY and ENCRYPTION_KEY

# 3) backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && alembic upgrade head && uvicorn app.main:app --reload --port 8000

# 4) frontend (new terminal)
cd apps/web && npm install && npm run dev

# 5) WhatsApp bridge (new terminal)
cd apps/whatsapp && go run .
```

El puente escucha solo en `127.0.0.1:3101` y tiene que quedarse corriendo junto
al backend. Guarda las claves de sesión en el almacén configurado con
`WHATSAPP_STORE_URL` (un archivo SQLite local, `file:whatsmeow.db`, por defecto;
una URL `postgres://` también funciona). Mira `.env.example` para la lista
completa de variables (`DATABASE_URL`, `BACKEND_URL`, `WHATSAPP_BRIDGE_URL`,
`WHATSAPP_BRIDGE_PORT`…).

## Conectar WhatsApp

1. Abre **Clientes → el cliente → Canales → WhatsApp → Configurar**.
2. Elige uno de los agentes de ese cliente y pulsa **Conectar con código QR**.
3. En el teléfono: **WhatsApp → Ajustes → Dispositivos vinculados → Vincular un
   dispositivo**, escanea el QR y espera a **Conectado**.

Los mensajes entrantes aparecen en el **Inbox** de la agencia y en el portal del
cliente. Pulsa **Tomar la conversación** para responder como persona (la IA se
pausa) y **Devolver a la IA** para continuar. Al reiniciar, el puente recarga las
sesiones activas desde su almacén de sesiones y se reconecta automáticamente: no
hace falta un QR nuevo salvo que WhatsApp termine la sesión, se desvincule el
dispositivo o cambie `ENCRYPTION_KEY`.

## Tests

Dentro de Docker:

```bash
make test   # backend pytest + rebuild the web/whatsapp validation stages
```

En local:

```bash
cd apps/api && ../../.venv/bin/pytest -q     # backend (needs the openlivery_test DB)
cd apps/whatsapp && go test ./... && go vet ./...
cd apps/web && npm run lint && npm run build
```

Volver a probar las migraciones desde cero:

```bash
cd apps/api && alembic downgrade base && alembic upgrade head
```

## Advertencias de WhatsApp / whatsmeow

whatsmeow se conecta al protocolo multidispositivo de **WhatsApp Web**; el número
se vincula como un dispositivo más mediante QR. **No** es la API oficial de
WhatsApp Business Cloud, y este proyecto no está afiliado ni respaldado por
WhatsApp ni por Meta.

- WhatsApp puede cambiar su protocolo o revocar una sesión o un dispositivo sin
  avisar.
- La automatización abusiva, el spam o los envíos masivos pueden hacer que
  restrinjan un número. Usa solo números autorizados por cada cliente y respeta
  los términos de WhatsApp.
- El QR vincula la cuenta mientras es válido: nunca lo compartas ni publiques una
  captura.
- La integración maneja conversaciones uno a uno (texto, más notas de voz
  transcritas e imágenes descritas cuando las capacidades del agente están
  activas). Ignora grupos, estados, canales, documentos, ubicaciones, reacciones
  y llamadas.
- Una cuenta de WhatsApp pertenece a un cliente; otro cliente necesita otro
  número. `apps/whatsapp/go.mod` fija una versión exacta de whatsmeow.

## Resolución de problemas

- **Puertos ocupados.** Sobrescríbelos en la misma línea:
  `API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up`.
- **Un servicio no está sano.** Revisa sus logs con `make logs SERVICE=api` (o
  `web`, `whatsapp`, `db`) y `make ps` para ver el estado.
- **La sesión no persiste, o el login entra en bucle detrás de HTTPS.** Asegúrate
  de tener `COOKIE_SECURE=true` y de estar llegando a la app por TLS.
- **Las claves de proveedor o la sesión de WhatsApp dejaron de descifrarse.**
  Cambió `ENCRYPTION_KEY`: restaura el valor original desde tu copia.
- **WhatsApp pide un QR nuevo tras reiniciar.** Solo es normal si WhatsApp
  terminó la sesión, se desvinculó el dispositivo o cambió `ENCRYPTION_KEY`; si
  no, el puente recarga solo las sesiones activas desde su almacén de sesiones.
