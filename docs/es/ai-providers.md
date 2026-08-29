# Proveedores de IA

> Read in English: [ai-providers.md](../en/ai-providers.md)

OpenLivery no incluye un proveedor de IA propio. En su lugar, cada agencia trae su propia clave: pegas una API key de un proveedor compatible, OpenLivery la guarda cifrada y todos los agentes de esa agencia la usan para hablar con un modelo. Así mantienes el control de la facturación, las cuotas y los datos.

## Trae tu propia clave

Las claves se configuran por agencia, una clave por proveedor. Abre **Settings**, busca la tarjeta del proveedor y pega tu clave. Al guardarla, OpenLivery primero valida la clave contra el proveedor (lista `{base_url}/models`); si la comprobación falla, no se guarda nada. Solo tras una validación correcta se persiste la clave.

Las claves guardadas nunca se devuelven completas al navegador: la interfaz solo muestra un valor enmascarado. En disco, la clave se cifra con una clave derivada de `ENCRYPTION_KEY` y se descifra bajo demanda cuando un agente la necesita, de modo que rotar o perder ese secreto hace ilegibles todas las claves guardadas. Consulta [Configuración](configuration.md) para saber cómo se define `ENCRYPTION_KEY` y por qué nunca debe cambiar.

## Proveedores compatibles

Hay dos proveedores compatibles de fábrica, cada uno con una base URL fija:

| Proveedor | Base URL | Modelos de ejemplo |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.6-sol`, `gpt-5.4-mini`, `gpt-4.1` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` |

Las claves de OpenAI se envían como bearer token; las de Anthropic usan la cabecera `x-api-key` junto con la cabecera `anthropic-version`. Internamente OpenLivery llama a la OpenAI Responses API y a la Anthropic Messages API.

### Cualquier endpoint compatible con OpenAI

La `base_url` y el `model` son ajustes por conexión, así que funciona cualquier endpoint compatible con OpenAI. La prueba de conexión simplemente hace un `GET` a `{base_url}/models` e informa cuántos modelos puede ver la clave. Mientras tu endpoint hable la API de OpenAI (o de Anthropic) y exponga una lista `/models`, puedes apuntar OpenLivery hacia él.

## Presets de modelos

La interfaz de Settings y el asistente de agentes ofrecen listas de modelos predefinidas para que no tengas que memorizar IDs. Provienen directamente de `apps/web/lib/providers.ts`.

**OpenAI:** `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`.

**Anthropic:** `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5`.

### Modelos de visión y audio

Algunas capacidades usan conjuntos de modelos específicos en lugar del modelo de chat:

- **Visión (`IMAGE_MODELS`)** para entender imágenes: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.5`, `gpt-5.4`, `gpt-5`, `gpt-5-mini`.
- **Transcripción (`AUDIO_MODELS`)** para entender audio: `gpt-transcribe`, `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe-diarize`.

## Elegir un modelo por agente

La clave del proveedor se define una vez por agencia, pero cada agente elige su propio proveedor y modelo. Lo haces al crear o editar un agente, escogiendo entre los presets anteriores (o escribiendo un ID personalizado para un endpoint compatible). Consulta [Agentes](agents.md) para ver cómo se combinan la elección de modelo, las instrucciones y el conocimiento.

## Siguientes pasos

- [Agentes](agents.md) — elige un modelo y escribe instrucciones.
- [Configuración](configuration.md) — `ENCRYPTION_KEY` y otros secretos.
- [Base de conocimiento](knowledge-base.md) — da contexto, Q&A y PDFs a un agente.
