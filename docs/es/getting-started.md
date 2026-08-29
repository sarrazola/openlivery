# Primeros pasos

> Read in English: [getting-started.md](../en/getting-started.md)

OpenLivery se ejecuta como tres servicios más PostgreSQL, orquestados por Docker Compose. La forma más rápida de probarlo es clonar el repositorio, generar los secretos y levantar el stack con un solo comando.

## Requisitos

Necesitas [Docker](https://docs.docker.com/get-docker/) — Docker Desktop, o Docker Engine con el plugin de Compose. No se instala nada más en el host; cada servicio (frontend, backend, puente de WhatsApp y base de datos) se ejecuta en un contenedor.

## Instalar y ejecutar

```bash
git clone https://github.com/sarrazola/openlivery.git
cd openlivery
./scripts/generate-docker-env.sh   # crea .env.docker con secretos aleatorios (gitignored)
make up                            # construye imágenes, inicia servicios y migra
```

`make up` envuelve a Docker Compose: construye las imágenes, inicia los cuatro servicios y aplica las migraciones de la base de datos antes de que la API acepte tráfico.

## Abre la aplicación

Cuando el stack esté saludable:

- **App** — [http://localhost:3000](http://localhost:3000)
- **Docs de la API (OpenAPI)** — [http://localhost:8000/docs](http://localhost:8000/docs)

Si esos puertos ya están en uso, sobrescríbelos en línea:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

¿Prefieres no construir en local? `make pull` ejecuta las imágenes prediseñadas publicadas en GHCR en lugar de construir desde el código.

## Primeros pasos

1. **Crea tu agencia** en la primera pantalla — es el espacio de trabajo principal que posee todo lo demás.
2. Abre **Ajustes** y añade una clave de OpenAI y/o Anthropic. La clave se verifica al guardarla. Consulta [Proveedores de IA](ai-providers.md).
3. Crea un **cliente** y luego un **agente** para ese cliente: elige proveedor y modelo, y escribe las instrucciones del agente. Consulta [Agentes](agents.md).
4. Añade conocimiento (contexto, pares de preguntas y respuestas, PDFs) y opcionalmente activa la comprensión de imágenes o audio. Consulta [Base de conocimiento](knowledge-base.md).
5. Abre el **Playground** para chatear con el agente, y luego conecta un número de [WhatsApp](whatsapp.md) o integra el [widget web](web-widget.md).

## Comandos útiles

| Comando | Qué hace |
| --- | --- |
| `make up` | Construye, inicia y migra todo el stack |
| `make down` | Detiene y elimina los contenedores |
| `make logs` | Sigue los logs de todos los servicios |
| `make migrate` | Aplica las migraciones pendientes |
| `make test` | Ejecuta la suite de pruebas del backend |
| `make help` | Lista todos los objetivos disponibles |

## Siguientes pasos

- [Configuración](configuration.md) — variables de entorno, secretos y puertos.
- [Arquitectura](architecture.md) — cómo encajan los servicios.
- [Autoalojamiento](self-hosting.md) — despliega en un servidor público con TLS y copias de seguridad.
