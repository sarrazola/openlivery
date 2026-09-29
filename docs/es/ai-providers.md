# Proveedores de IA

> Read in English: [ai-providers.md](../en/ai-providers.md)

OpenLivery no incluye un proveedor de IA propio. Cada agencia trae su propia clave: pegas una API key de **OpenRouter**, OpenLivery la guarda cifrada y todos los agentes de esa agencia la usan para hablar con cualquier modelo que OpenRouter ofrezca. Así mantienes el control de la facturación, las cuotas y los datos, y cada agente tiene la misma puerta a OpenAI, Anthropic, Google, DeepSeek, xAI y el resto.

## Trae tu propia clave

Las claves se configuran por agencia. Abre **Ajustes**, busca la tarjeta de OpenRouter y pega tu clave (créala en [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)). Al guardarla, OpenLivery primero la valida contra OpenRouter (consulta `{base_url}/key`, que describe la clave y su crédito restante); si la verificación falla, no se guarda nada. Solo tras una validación exitosa se persiste la clave.

Las claves guardadas nunca se devuelven completas al navegador: la interfaz solo muestra un valor enmascarado. En disco, la clave se cifra con una clave derivada de `ENCRYPTION_KEY` y se descifra bajo demanda cuando un agente la necesita, así que rotar o perder ese secreto hace ilegible la clave guardada. Consulta [Configuración](configuration.md) para saber cómo se define `ENCRYPTION_KEY` y por qué nunca debe cambiar.

## Cómo se hacen las peticiones

OpenLivery llama a la API compatible con OpenAI de OpenRouter en `https://openrouter.ai/api/v1`:

| Capacidad | Endpoint |
| --- | --- |
| Respuestas de chat y llamadas a herramientas | `/chat/completions` |
| Comprensión de imágenes | `/chat/completions` con una parte de imagen |
| Transcripción de notas de voz | `/audio/transcriptions` |
| Embeddings de la base de conocimiento | `/embeddings` (`openai/text-embedding-3-small`) |

Cada respuesta de chat vuelve con el bloque de uso de OpenRouter, incluido lo que costó la llamada. OpenLivery guarda esa cifra con el registro de uso de la respuesta (`usage_records.cost_usd`), así que los reportes de costo leen números reales en vez de estimar con una tabla de precios.

## Identificadores de modelo

Los modelos se nombran por su slug de OpenRouter, `proveedor/modelo`: `openai/gpt-6-luna`, `anthropic/claude-sonnet-5`, `google/gemini-3.8-flash`. El asistente de creación y la página del agente ofrecen una lista curada de presets, agrupada por lo que una agencia realmente elige (los más rápidos y económicos, equilibrados, los más potentes), y aceptan cualquier otro slug escrito a mano. Los presets salen de `apps/web/lib/providers.ts` y se reflejan, con ventana de contexto, capacidades y precio de lista, en `apps/api/app/services/model_catalog.py` (`GET /api/catalog/models`).

### Modelos de visión y audio

Algunas capacidades usan conjuntos de modelos dedicados en lugar del modelo de chat:

- **Visión (`IMAGE_MODELS`)** para comprensión de imágenes: cualquier modelo de chat con visión del catálogo. El predeterminado es `openai/gpt-4.1`.
- **Transcripción (`AUDIO_MODELS`)** para comprensión de audio: `openai/gpt-4o-mini-transcribe` (predeterminado), `openai/gpt-4o-transcribe`, `openai/gpt-transcribe`.

## Elegir un modelo por agente

La clave se define una vez por agencia, pero cada agente elige su propio modelo. Lo haces al crear o editar un agente, escogiendo entre los presets anteriores o escribiendo un slug. Consulta [Agentes](agents.md) para ver cómo se combinan la elección de modelo, las instrucciones y el conocimiento.

## Actualizar desde claves de OpenAI y Anthropic

Las versiones anteriores a la migración `0042_openrouter` guardaban claves de OpenAI y Anthropic y usaban identificadores de modelo sin proveedor. La migración pasa todos los agentes a OpenRouter y reescribe sus modelos como slugs (`gpt-4.1-mini` pasa a `openai/gpt-4.1-mini`, `claude-sonnet-5` a `anthropic/claude-sonnet-5`, `whisper-1` a `openai/gpt-4o-mini-transcribe`). Las claves antiguas se eliminan, porque OpenRouter no puede usarlas: tras actualizar, agrega una clave de OpenRouter en Ajustes y los agentes vuelven a responder.

## Próximos pasos

- [Agentes](agents.md): elige un modelo y escribe instrucciones.
- [Configuración](configuration.md): `ENCRYPTION_KEY` y otros secretos.
- [Base de conocimiento](knowledge-base.md): dale contexto, preguntas y respuestas y PDFs a un agente.
