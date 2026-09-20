# Contribuir

> Read in English: [contributing.md](../en/contributing.md)

Docker es la forma más rápida de ejecutar OpenLivery, pero para el desarrollo diario normalmente querrás cada servicio corriendo en tu máquina con recarga en caliente. Esta guía cubre cómo ejecutar el backend, el frontend y el puente de WhatsApp localmente, las suites de pruebas, las migraciones y las convenciones del proyecto.

## Alcance de la instalación

Cada instalación sirve a una agencia con múltiples espacios de clientes. La
configuración inicial crea esa agencia y su propietario; después se cierra el
registro público. No añadas configuración, rutas de API ni flujos de interfaz
para registrar agencias adicionales. Conserva las comprobaciones de propiedad
y los datos existentes al modificar la configuración inicial o el acceso.

## Requisitos previos

Clona el repositorio y activa el guard de pre-commit una vez por clon:

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
git config core.hooksPath .githooks
```

El guard (`.githooks/pre-commit`) impide commitear archivos locales y cualquier contenido preparado marcado como interno. Necesitas Python 3.12, Node.js, Go 1.27+ y una instancia de PostgreSQL en ejecución a la que el backend pueda conectarse.

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
go run .                        # escucha en :3101
```

El puente es un único binario de Go (Go 1.27+); no hay paso de instalación. Ejecuta `go test ./...` para la suite de pruebas y `go vet ./...` para verificar el build.

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

Una migración corre en instalaciones que ya tienen datos y están atendiendo tráfico, así que aplican algunas reglas, cada una verificada por `apps/api/tests/test_migration_conventions.py`:

- **Un archivo por revisión, con su mismo nombre, y una sola cabeza.** Si `main` ganó una migración mientras trabajabas, rebasa la tuya sobre ella. Cuidado con copias sueltas de un archivo en `migrations/versions/`.
- **Un id de revisión de 32 caracteres como máximo.** Es lo que guarda la tabla de versiones de Alembic.
- **Sin nombres de esquema.** Deja las tablas sin calificar y no fijes `search_path` ni crees extensiones; una migración corre bajo el `search_path` que le dé su despliegue.
- **Un `downgrade()` que funcione.** Es el camino de vuelta cuando se revierte una versión.
- **`conversations` antes que las tablas de canales.** Una respuesta las bloquea en ese orden, y una migración que las tome al revés entra en deadlock con el tráfico en vivo.
- **Borrar datos es una decisión escrita.** Eliminar una tabla o columna, cambiar el tipo de una columna o borrar filas exige una línea `# contract: reviewed` que diga por qué la versión anterior sigue funcionando, o qué debe hacer antes quien opera la instalación. Es preferible borrar en una versión posterior a la que deja de leer el dato.
- **Una migración ya integrada no se edita.** Las instalaciones que la corrieron no la volverán a correr; agrega una revisión nueva.

Cada pull request ejecuta el workflow `Tests`: la suite del API, las migraciones aplicadas a una base vacía y las más recientes revertidas y aplicadas de nuevo, el lint y el build del web, y el `go vet` y `go test` del puente.

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
| WhatsApp | `go run .` | Ejecuta el puente en :3101 |
| WhatsApp | `go test ./...` | Ejecuta la suite de pruebas |
| WhatsApp | `go vet ./...` | Verifica el build |

## Próximos pasos

- [Arquitectura](architecture.md) — cómo encajan los servicios entre sí.
- [Configuración](configuration.md) — variables de entorno, secretos y puertos.
- [Auto-alojamiento](self-hosting.md) — despliega en un servidor público con TLS y copias de seguridad.
