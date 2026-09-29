"""The model catalog reads OpenRouter's lists and keeps working when it can't."""

from datetime import datetime, timedelta, timezone

from app.services import model_catalog as catalog


def _openrouter_chat(model_id, name, inputs, outputs=("text",), prompt="0.000002", completion="0.000008",
                     params=("tools", "temperature"), context=128_000, max_out=16_384):
    return {
        "id": model_id, "name": name, "context_length": context,
        "pricing": {"prompt": prompt, "completion": completion},
        "architecture": {"input_modalities": list(inputs), "output_modalities": list(outputs)},
        "supported_parameters": list(params),
        "top_provider": {"context_length": context, "max_completion_tokens": max_out},
    }


def test_the_catalog_is_what_openrouter_lists(monkeypatch):
    raw = [
        _openrouter_chat("openai/gpt-5.6-luna", "OpenAI: GPT-5.6 Luna", ("text", "image", "file"), prompt="0.0000002", completion="0.0000012", context=1_050_000, max_out=128_000),
        _openrouter_chat("deepseek/deepseek-v4-flash", "DeepSeek: V4 Flash", ("text",), params=("temperature",)),
        # Not something an agent can be pointed at: an alias, a batch-only endpoint, an image generator, a plain embedding.
        _openrouter_chat("~google/gemini-flash-latest", "Gemini Flash (latest)", ("text",)),
        _openrouter_chat("google/gemini-3.8-flash:batch", "Google: Gemini 3.8 Flash (batch)", ("text",)),
        _openrouter_chat("black-forest/flux", "Flux", ("text",), outputs=("image",)),
        # A price OpenRouter only knows at request time is no list price.
        _openrouter_chat("openrouter/auto", "Auto Router", ("text",), prompt="-1", completion="-1"),
    ]
    embeddings = [
        {"id": "openai/text-embedding-3-small", "name": "OpenAI: text-embedding-3-small", "context_length": 8_192, "pricing": {"prompt": "0.00000002"}},
        {"id": "liquid/tiny-embedding", "name": "LiquidAI: tiny", "context_length": 512, "pricing": {"prompt": "0"}},
    ]
    monkeypatch.setattr(catalog, "fetch_catalog", lambda: (
        [m for m in (catalog._parse_model(r) for r in raw) if m],
        [m for m in (catalog._parse_embedding(r) for r in embeddings) if m],
    ))
    catalog._current = None

    ids = [m.id for m in catalog.list_models()]
    assert ids == ["deepseek/deepseek-v4-flash", "openai/gpt-5.6-luna", "openrouter/auto"]
    luna = catalog.get_model("openai/gpt-5.6-luna")
    assert luna.label == "GPT-5.6 Luna" and luna.provider == "openai"
    assert luna.supports_vision and luna.supports_tools and luna.context_window == 1_050_000 and luna.max_output_tokens == 128_000
    assert luna.input_price_per_1k == 0.0002 and luna.output_price_per_1k == 0.0012
    flash = catalog.get_model("deepseek/deepseek-v4-flash")
    assert not flash.supports_vision and not flash.supports_tools
    assert catalog.get_model("openrouter/auto").input_price_per_1k == 0.0

    # Embeddings too short for a knowledge-base chunk are left out.
    assert [m.id for m in catalog.list_embedding_models()] == ["openai/text-embedding-3-small"]
    assert catalog.get_embedding_model("openai/text-embedding-3-small").input_price_per_1k == 0.00002

    offered = catalog.available_models()
    assert offered["chat"] == {"openrouter": ids}
    assert offered["image"] == ["openai/gpt-5.6-luna"]
    assert offered["embedding"] == ["openai/text-embedding-3-small"]
    # Transcription comes from the setting, since OpenRouter lists it nowhere.
    assert offered["audio"] == ["openai/gpt-4o-mini-transcribe", "openai/gpt-4o-transcribe", "openai/gpt-transcribe"]
    assert catalog.get_model("openai/gpt-4o-transcribe").family == "transcribe"


def test_a_failed_refresh_keeps_the_last_list(monkeypatch):
    good = [catalog.ModelInfo("openai/gpt-5.6-luna", "openai", "GPT-5.6 Luna", "openai", 1, 1, True, True, 0.0002, 0.0012)]
    catalog.set_snapshot(good, [], fetched_at=datetime.now(timezone.utc) - timedelta(hours=2))
    assert catalog._current.stale()

    def down():
        raise RuntimeError("openrouter is down")

    monkeypatch.setattr(catalog, "fetch_catalog", down)
    assert [m.id for m in catalog.list_models()] == ["openai/gpt-5.6-luna"]
    # And before OpenRouter ever answered, the defaults still let an agent be created.
    catalog._current = None
    assert catalog.get_model("openai/gpt-6-luna") is not None
    assert catalog.DEFAULT_EMBEDDING_MODEL in [m.id for m in catalog.list_embedding_models()]
    assert catalog.DEFAULT_AUDIO_MODEL in catalog.audio_models()
