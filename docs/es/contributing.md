# Contribuir

> Read in English: [contributing.md](../en/contributing.md)

Docker es la forma más rápida de ejecutar OpenLivery, pero para el desarrollo diario normalmente querrás cada servicio corriendo en tu máquina con recarga en caliente. Esta guía cubre cómo ejecutar el backend, el frontend y el puente de WhatsApp localmente, las suites de pruebas, las migraciones y las convenciones del proyecto.

## Requisitos previos

Clona el repositorio y activa el guard de pre-commit una vez por clon:

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
git config core.hooksPath .githooks
```

El guard (`.githooks/pre-commit`) impide commitear archivos locales y cualquier contenido preparado marcado como interno. Necesitas Python 3.12, Node.js y una instancia de PostgreSQL en ejecución a la que el backend pueda conectarse.

## Backend (apps/api)

Copia `.env.example` a `.env` y apunta `DATABASE_URL` a tu PostgreSQL. Instala las dependencias, aplica las migraciones y arranca el servidor con recarga:

```bash
cd apps/api
pip install -r requirements.txt
alembic upgrade head            # las migraciones deben ejecutarse antes de arrancar
uvicorn app.main:app --reload --port 8000
```

La documentación OpenAPI se sirve en [http://localhost:8000/docs](http://localhost:8000/docs).

## Frontend (apps/web)

```bash
cd apps/web
npm install
npm run dev                     # http://localhost:3000
```

Usa `npm run lint` antes de commitear y `npm run build` para verificar un build de producción. Ten en cuenta que esto es Next.js 16 (App Router) — revisa la documentación incluida en `node_modules/next/dist/docs/` antes de escribir código Next.js no trivial, ya que varias APIs difieren de versiones anteriores.

## Puente de WhatsApp (apps/whatsapp)

```bash
cd apps/whatsapp
npm install
npm run dev                     # tsx watch, escucha en :3101
```

Ejecuta `npm test` para la suite de pruebas y `npm run build` para hacer typecheck con `tsc`.

## Pruebas

Las pruebas del backend necesitan una base de datos **separada** — nunca las apuntes a tu base de datos de desarrollo. Por defecto usan `openlivery_test` en localhost y crean/eliminan todas las tablas por prueba. Cambia el destino con `TEST_DATABASE_URL`:

```bash
cd apps/api
pytest -q
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/openlivery_test pytest -q
```

Ejecuta una sola prueba por su identificador:

```bash
pytest tests/test_flows.py::test_register_login_logout_and_me -v
```

## Migraciones de base de datos

Cualquier cambio de esquema requiere una nueva migración de Alembic — Docker ejecuta `alembic upgrade head` al arrancar el backend, así que un cambio sin migración romperá el stack en contenedores. Genera una tras editar los modelos, revisa el archivo generado y luego aplícala.

## Convenciones

Todo el código, los identificadores, los comentarios, los mensajes de commit y la documentación se escriben en **inglés**, siempre. Lo único que se localiza es la interfaz de usuario final, a través del sistema tipado de i18n en `apps/web/lib/i18n` (inglés por defecto, español por ahora). Nunca introduzcas texto que no sea inglés en el código o la documentación — coloca el texto visible para el usuario detrás de claves de i18n.

## Referencia de comandos

| Servicio | Comando | Qué hace |
| --- | --- | --- |
| Backend | `pip install -r requirements.txt` | Instala las dependencias de Python |
| Backend | `alembic upgrade head` | Aplica las migraciones pendientes |
| Backend | `uvicorn app.main:app --reload --port 8000` | Ejecuta la API con recarga en caliente |
| Backend | `pytest -q` | Ejecuta la suite de pruebas |
| Frontend | `npm install` | Instala las dependencias |
| Frontend | `npm run dev` | Ejecuta el servidor de desarrollo en :3000 |
| Frontend | `npm run lint` | Analiza con ESLint |
| Frontend | `npm run build` | Build de producción |
| WhatsApp | `npm run dev` | Ejecuta el puente en :3101 |
| WhatsApp | `npm test` | Ejecuta la suite de pruebas |
| WhatsApp | `npm run build` | Typecheck con tsc |

## Próximos pasos

- [Arquitectura](architecture.md) — cómo encajan los servicios entre sí.
- [Configuración](configuration.md) — variables de entorno, secretos y puertos.
- [Auto-alojamiento](self-hosting.md) — despliega en un servidor público con TLS y copias de seguridad.
