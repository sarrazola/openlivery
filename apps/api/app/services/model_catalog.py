"""AI model catalog, read live from OpenRouter (backend source of truth).

Models are OpenRouter slugs (``vendor/model``). The catalog is what OpenRouter
serves right now: its ``/models`` list for chat (and, through the image
modality, vision) and its ``/embeddings/models`` list for the knowledge base,
each with the context window, capabilities and list price OpenRouter reports.
Nothing about a model is written down here; a new model on OpenRouter shows
up on the next refresh, and a retired one goes away.

The one exception is transcription. OpenRouter serves speech-to-text through
its audio endpoint but lists those models nowhere its API exposes, so the
offer comes from ``TRANSCRIPTION_MODELS`` (a setting, not a price list): what
a transcription cost is what OpenRouter reports for the call, reconciled after
the fact like any other reply.

The list is cached in process and refreshed after CATALOG_TTL; a refresh that
fails keeps serving the last good list, so a hiccup at OpenRouter never empties
the pickers. A deployment may narrow ``available_models`` (to the models a
shared key serves, say), which is why the frontend asks for it instead of
trusting a static list.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings

logger = logging.getLogger("app.model_catalog")

CATALOG_TTL = timedelta(hours=1)
FETCH_TIMEOUT = 8.0
# The knowledge base chunks at ~1,800 characters; an embedding model that
# takes less than this cannot embed a chunk, so it is left out.
MIN_EMBEDDING_CONTEXT = 2_000
# Standard approximation to estimate tokens without a tokenizer: ~4 chars/token.
CHARS_PER_TOKEN = 4

# Transcription model an agent gets unless it picks another one.
DEFAULT_AUDIO_MODEL = "openai/gpt-4o-mini-transcribe"
# Embedding model an agent's knowledge base uses unless it picks another one.
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"


@dataclass(frozen=True)
class ModelInfo:
    id: str
    # The vendor behind the slug, for grouping and labels.
    provider: str
    label: str
    family: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    # List price per 1,000 tokens, in USD.
    input_price_per_1k: float
    output_price_per_1k: float
    badge: str = ""
    note: str = ""


@dataclass(frozen=True)
class EmbeddingModelInfo:
    id: str
    provider: str
    label: str
    # Longest input the model embeds, in tokens.
    context_window: int
    # List price per 1,000 input tokens, in USD (embeddings have no output).
    input_price_per_1k: float
    note: str = ""


@dataclass(frozen=True)
class Snapshot:
    """One read of the catalog, chat and embedding models together."""

    models: tuple[ModelInfo, ...]
    embeddings: tuple[EmbeddingModelInfo, ...]
    # Speech-to-text, never offered as chat.
    audio: tuple[ModelInfo, ...]
    fetched_at: datetime | None

    def stale(self) -> bool:
        return self.fetched_at is None or datetime.now(timezone.utc) - self.fetched_at > CATALOG_TTL


def _vendor(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else ""


def _label(name: str, model_id: str) -> str:
    """OpenRouter names models "Vendor: Model"; the vendor is already in the
    slug, so the label keeps the model part."""
    name = (name or "").strip()
    if ": " in name:
        return name.split(": ", 1)[1].strip() or name
    return name or model_id


def _per_1k(value) -> float:
    """OpenRouter prices per token, as strings; -1 marks a price it will only
    know at request time, which is no list price at all."""
    try:
        price = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    # Rounded past any figure OpenRouter uses, so 2e-7 a token reads 0.0002.
    return round(price * 1000, 10) if price > 0 else 0.0


def _parse_model(raw: dict) -> ModelInfo | None:
    model_id = raw.get("id") or ""
    architecture = raw.get("architecture") or {}
    inputs = set(architecture.get("input_modalities") or [])
    outputs = set(architecture.get("output_modalities") or [])
    # Aliases (``~vendor/latest``) and batch-only endpoints are not something
    # an agent can be pointed at.
    if not model_id or model_id.startswith("~") or model_id.endswith(":batch"):
        return None
    if "text" not in inputs or "text" not in outputs:
        return None
    pricing = raw.get("pricing") or {}
    top = raw.get("top_provider") or {}
    context = int(raw.get("context_length") or top.get("context_length") or 0)
    return ModelInfo(
        id=model_id,
        provider=_vendor(model_id),
        label=_label(raw.get("name") or "", model_id),
        family=_vendor(model_id),
        context_window=context,
        max_output_tokens=int(top.get("max_completion_tokens") or min(context, 16_384) or 0),
        supports_tools="tools" in (raw.get("supported_parameters") or []),
        supports_vision="image" in inputs,
        input_price_per_1k=_per_1k(pricing.get("prompt")),
        output_price_per_1k=_per_1k(pricing.get("completion")),
    )


def _parse_embedding(raw: dict) -> EmbeddingModelInfo | None:
    model_id = raw.get("id") or ""
    context = int(raw.get("context_length") or 0)
    if not model_id or model_id.startswith("~") or context < MIN_EMBEDDING_CONTEXT:
        return None
    pricing = raw.get("pricing") or {}
    return EmbeddingModelInfo(
        id=model_id,
        provider=_vendor(model_id),
        label=_label(raw.get("name") or "", model_id),
        context_window=context,
        input_price_per_1k=_per_1k(pricing.get("prompt")),
    )


def fetch_catalog() -> tuple[list[ModelInfo], list[EmbeddingModelInfo]]:
    """Read OpenRouter's lists. Public endpoints, no key needed."""
    from .providers import DEFAULT_PROVIDER, base_url_for

    base = base_url_for(DEFAULT_PROVIDER).rstrip("/")
    with httpx.Client(timeout=FETCH_TIMEOUT) as client:
        chat = client.get(f"{base}/models")
        chat.raise_for_status()
        embeddings = client.get(f"{base}/embeddings/models")
        embeddings.raise_for_status()
    models = [m for m in (_parse_model(raw) for raw in chat.json().get("data") or []) if m]
    embedding_models = [m for m in (_parse_embedding(raw) for raw in embeddings.json().get("data") or []) if m]
    return models, embedding_models


def _transcription_ids() -> list[str]:
    raw = getattr(get_settings(), "transcription_models", "") or ""
    ids = [m.strip() for m in raw.split(",") if m.strip()]
    return ids or [DEFAULT_AUDIO_MODEL]


def _audio_entries(priced: dict[str, ModelInfo] | None = None) -> tuple[ModelInfo, ...]:
    """The transcription models, as bare entries: OpenRouter lists them
    nowhere, so they carry no list price unless a snapshot supplied one."""
    priced = priced or {}
    return tuple(
        priced.get(model_id) or ModelInfo(
            model_id, _vendor(model_id), _label("", model_id), "transcribe", 16_000, 2_000, False, False, 0.0, 0.0,
        )
        for model_id in _transcription_ids()
    )


def _seed() -> Snapshot:
    """What the catalog offers before OpenRouter has answered once: the
    defaults, so an agent can still be created, and nothing priced."""
    chat = ModelInfo("openai/gpt-5.6-luna", "openai", "GPT-5.6 Luna", "openai", 0, 0, True, True, 0.0, 0.0)
    embedding = EmbeddingModelInfo(DEFAULT_EMBEDDING_MODEL, "openai", "text-embedding-3-small", 8_192, 0.0)
    return Snapshot((chat,), (embedding,), _audio_entries(), None)


_lock = threading.Lock()
_current: Snapshot | None = None


def _ordered(models) -> tuple:
    """By vendor, then name: how the pickers list them, whatever the source."""
    return tuple(sorted(models, key=lambda m: (m.provider, m.label.lower())))


def set_snapshot(models, embeddings, *, audio=None, fetched_at: datetime | None = None) -> None:
    """Install a catalog directly, for tests and for deployments that ship a
    fixed list instead of reading OpenRouter."""
    global _current
    priced = {m.id: m for m in (audio or ())}
    _current = Snapshot(_ordered(models), _ordered(embeddings), _audio_entries(priced),
                        fetched_at or datetime.now(timezone.utc))


def _snapshot() -> Snapshot:
    """The current catalog, refreshed when stale; a failed refresh keeps the
    last good list."""
    global _current
    if _current is not None and not _current.stale():
        return _current
    with _lock:
        if _current is not None and not _current.stale():
            return _current
        try:
            models, embeddings = fetch_catalog()
            audio = {m.id: m for m in _current.audio} if _current else {}
            _current = Snapshot(_ordered(models), _ordered(embeddings), _audio_entries(audio), datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001 - never empty the pickers over a network hiccup
            logger.warning("Could not refresh the model catalog from OpenRouter", exc_info=True)
            if _current is None:
                _current = _seed()
            else:
                # Serve the stale list and try again on the next read after a short back-off.
                _current = Snapshot(_current.models, _current.embeddings, _current.audio,
                                    datetime.now(timezone.utc) - CATALOG_TTL + timedelta(minutes=5))
        return _current


def list_models() -> list[ModelInfo]:
    """Every chat model OpenRouter serves, by vendor and name."""
    return list(_snapshot().models)


def get_model(model_id: str) -> ModelInfo | None:
    """Metadata for a model by its ID (chat or transcription), or None."""
    snapshot = _snapshot()
    for model in (*snapshot.models, *snapshot.audio):
        if model.id == model_id:
            return model
    return None


def list_embedding_models() -> list[EmbeddingModelInfo]:
    return list(_snapshot().embeddings)


def get_embedding_model(model_id: str) -> EmbeddingModelInfo | None:
    for model in _snapshot().embeddings:
        if model.id == model_id:
            return model
    return None


def estimate_tokens(text: str) -> int:
    """Quick token estimate (~4 characters per token)."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def image_models() -> list[str]:
    """Chat models that accept images: the image-understanding capability."""
    return [model.id for model in _snapshot().models if model.supports_vision]


def audio_models() -> list[str]:
    """Speech-to-text models, for the audio capability."""
    return [model.id for model in _snapshot().audio]


def available_models() -> dict:
    """Model ids a workspace can pick, per provider and capability.

    A stock install offers everything OpenRouter serves. A deployment may
    narrow this (for example to the models its managed credit can serve),
    which is why the frontend asks instead of trusting its static lists.
    """
    snapshot = _snapshot()
    return {
        "chat": {"openrouter": [model.id for model in snapshot.models]},
        "image": [model.id for model in snapshot.models if model.supports_vision],
        "audio": [model.id for model in snapshot.audio],
        "embedding": [model.id for model in snapshot.embeddings],
    }
