# Autoalojamiento

> Read in English: [self-hosting.md](../en/self-hosting.md)

Ejecutar OpenLivery en un servidor usa el mismo stack de Docker Compose que en local, más tu propio proxy inverso por delante para el TLS. Una instancia equivale a una agencia, y todos los datos viven en volúmenes que respaldas y conservas entre actualizaciones.

## Desplegar en un servidor público

El stack sirve HTTP plano a través de un gateway Caddy de un solo origen: `/api/*` va al backend y todo lo demás al frontend. El TLS lo proporciona el operador — no hay TLS incluido ni `make deploy`. Coloca tu propio proxy inverso (Caddy, nginx, Traefik o un balanceador de carga en la nube) delante del puerto del gateway para terminar HTTPS con tu dominio.

1. Clona el repositorio y levanta el stack como en [Primeros pasos](getting-started.md):

   ```bash
   git clone https://github.com/sarrazola/openlivery.git
   cd openlivery
   ./scripts/generate-docker-env.sh
   make up
   ```

2. El gateway escucha en `${WEB_PORT}` (por defecto `3000`), enlazado a `127.0.0.1`. Apunta tu proxy inverso a `127.0.0.1:3000`. Como la app y la API comparten un mismo origen, redirige el **dominio completo** a ese único puerto.
3. Configura `COOKIE_SECURE=true` en `.env.docker` y reinicia, para que la cookie de sesión solo se envíe por TLS.

Mantén la base de datos, la API y el puente de WhatsApp privados dejando `BIND_HOST=127.0.0.1` (el valor por defecto); solo tu proxy inverso debe estar expuesto a internet. Para la lista completa de variables consulta [Configuración](configuration.md).

Un ejemplo mínimo con Caddy en el host:

```caddyfile
agency.example.com {
	reverse_proxy 127.0.0.1:3000
}
```

## Datos persistentes

Todo el estado vive en volúmenes de Docker con nombre, por lo que `make down` y las actualizaciones lo conservan:

| Volumen | Contenido |
| --- | --- |
| `postgres_data` | La base de datos PostgreSQL — agencias, agentes, conversaciones, claves de proveedor cifradas y el estado cifrado de la sesión de WhatsApp. |
| `backend_storage` | Archivos subidos (por ejemplo, los PDF de la base de conocimiento). |

La `ENCRYPTION_KEY` descifra las claves de API de los proveedores y las sesiones de WhatsApp. **Nunca la cambies** una vez almacenados los secretos, o quedarán irrecuperables — trátala como parte de tu copia de seguridad.

## Copias de seguridad y restauración

Exporta PostgreSQL sin detener la app:

```bash
mkdir -p backups
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/openlivery.dump
```

Guarda también `.env.docker` en un gestor de secretos: un volcado con claves de API o una sesión de WhatsApp necesita la misma `ENCRYPTION_KEY` para descifrarse. Restaura (reemplaza los datos de la base de datos de destino — haz una copia antes):

```bash
docker compose --env-file .env.docker stop api whatsapp
docker compose --env-file .env.docker exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/openlivery.dump
docker compose --env-file .env.docker start api whatsapp
```

## Actualizaciones

Descarga la nueva versión y reconstruye — los volúmenes de datos quedan intactos:

```bash
git pull
make up        # reconstruye y reinicia; tu proxy inverso sigue por delante
```

El backend ejecuta `alembic upgrade head` al arrancar, por lo que los cambios de esquema se aplican sin borrar `postgres_data`. ¿Ejecutas desde imágenes prediseñadas? Usa `make pull` (fija una versión con `OPENLIVERY_VERSION=v1.2.3 make pull`). Haz una copia de seguridad antes.

## Dominios personalizados para portales de cliente

Por defecto el portal de un cliente vive en `tu-dominio/portal/<slug>`. También puedes servirlo bajo el dominio propio del cliente con TLS bajo demanda, un override opcional que monta `docker/Caddyfile.ondemand` y publica los puertos 80/443 en el gateway. El recorrido completo — el `docker-compose.override.yml`, los registros DNS y la verificación — está en [Portal de cliente](client-portal.md).

## Ejecutar sin Docker

Para una configuración local sin contenedores ejecutas cada servicio a mano. Requisitos: Python 3.12+, Node.js 20+, PostgreSQL 14+.

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
cd apps/whatsapp && npm install && npm run start
```

El puente escucha solo en `127.0.0.1:3101` y debe seguir en ejecución junto al backend. Consulta `.env.example` para la lista completa de variables (`DATABASE_URL`, `BACKEND_URL`, `WHATSAPP_BRIDGE_URL`, `WHATSAPP_BRIDGE_PORT`, …).

## Solución de problemas

- **Puertos ya en uso.** Sobrescríbelos en línea: `API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up`.
- **Un servicio está unhealthy.** Revisa sus logs con `make logs SERVICE=api` (o `web`, `whatsapp`, `db`) y `make ps` para ver el estado.
- **La sesión no persiste / bucle de inicio de sesión tras HTTPS.** Asegúrate de que `COOKIE_SECURE=true` está configurado y de que accedes a la app por TLS.
- **Las claves de proveedor o la sesión de WhatsApp dejaron de descifrarse.** La `ENCRYPTION_KEY` cambió — restaura el valor original desde tu copia de seguridad.
- **WhatsApp pide un nuevo QR tras reiniciar.** Es normal solo si WhatsApp terminó la sesión, se desvinculó el dispositivo o cambió la `ENCRYPTION_KEY`; de lo contrario el puente recarga las sesiones habilitadas desde PostgreSQL automáticamente.
