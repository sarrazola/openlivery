import asyncio
import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Agent, KnowledgeChunk
from app.routers import agents as agents_router
from app.services import knowledge as knowledge_module
from tests.conftest import TestingSession


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


def _reader_for(text: str):
    class _Reader:
        def __init__(self, _path):
            self.pages = [_FakePage(text)]

    return _Reader


def _setup_agent(client: TestClient) -> str:
    customer = client.post("/api/clients", json={"name": "Docs Co", "is_active": True}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-5", "name": "Doco", "instructions": "", "personality": ""},
    ).json()
    assert agent["embedding_model"] == "openai/text-embedding-3-small"
    return agent["id"]


def _fake_embed(dimension: int):
    async def _embed(base_url, api_key, texts, model="openai/text-embedding-3-small"):
        return [[1.0] * dimension for _ in texts]

    return _embed


def test_reindex_after_changing_the_embedding_model(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    monkeypatch.setattr(agents_router, "PdfReader", _reader_for("Our warranty lasts two years.\n\nReturns are free."))
    monkeypatch.setattr(knowledge_module, "embed_texts", _fake_embed(3))
    uploaded = client.post(f"/api/agents/{agent_id}/documents", files={"file": ("w.pdf", b"%PDF-test", "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["indexed_model"] == "openai/text-embedding-3-small"
    assert uploaded.json()["chunk_count"] == 1

    # Switching the model leaves the old chunks in place until a reindex.
    changed = client.patch(f"/api/agents/{agent_id}", json={"embedding_model": "qwen/qwen3-embedding-8b"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["embedding_model"] == "qwen/qwen3-embedding-8b"
    listed = client.get(f"/api/agents/{agent_id}/documents").json()
    assert listed[0]["indexed_model"] == "openai/text-embedding-3-small"

    monkeypatch.setattr(knowledge_module, "embed_texts", _fake_embed(5))
    reindexed = client.post(f"/api/agents/{agent_id}/documents/reindex")
    assert reindexed.status_code == 200, reindexed.text
    assert reindexed.json()[0]["indexed_model"] == "qwen/qwen3-embedding-8b"
    with TestingSession() as db:
        chunks = db.scalars(select(KnowledgeChunk)).all()
        assert [(c.embedding_model, len(c.embedding)) for c in chunks] == [("qwen/qwen3-embedding-8b", 5)]

    # A provider that returns nothing is reported, not swallowed.
    monkeypatch.setattr(knowledge_module, "embed_texts", AsyncMock(return_value=None))
    failed = client.post(f"/api/agents/{agent_id}/documents/reindex")
    assert failed.status_code == 502

    # Bad slugs are rejected.
    assert client.patch(f"/api/agents/{agent_id}", json={"embedding_model": "not a slug"}).status_code == 422


def test_semantic_search_uses_only_the_agent_model_and_the_best_chunks(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    big = "\n\n".join(f"Paragraph {i} about topic {i % 7}. " * 12 for i in range(150))
    assert len(big) > knowledge_module.MAX_FULL_CONTEXT_CHARS
    monkeypatch.setattr(agents_router, "PdfReader", _reader_for(big))
    monkeypatch.setattr(knowledge_module, "embed_texts", _fake_embed(2))
    assert client.post(f"/api/agents/{agent_id}/documents", files={"file": ("big.pdf", b"%PDF-test", "application/pdf")}).status_code == 201

    with TestingSession() as db:
        agent = db.get(Agent, __import__("uuid").UUID(agent_id))
        chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.agent_id == agent.id).order_by(KnowledgeChunk.position)).all()
        assert len(chunks) > knowledge_module.MAX_SEMANTIC_CHUNKS
        # Give each chunk a distinct direction; mark two as coming from another model.
        for index, chunk in enumerate(chunks):
            chunk.embedding = [1.0, float(index)]
        chunks[0].embedding_model = "google/gemini-embedding-2"
        chunks[1].embedding_model = "google/gemini-embedding-2"
        db.commit()

        monkeypatch.setattr(knowledge_module, "embed_query", AsyncMock(return_value=[1.0, 0.0]))
        result = asyncio.run(knowledge_module.retrieve_knowledge(db, agent, "topic"))
        # Ranked by cosine against [1, 0]: lower positions first, but the two
        # foreign-model chunks (positions 0 and 1) are never candidates.
        assert chunks[0].content[:40] not in result.text and chunks[1].content[:40] not in result.text
        assert chunks[2].content[:40] in result.text
        assert result.text.count("DOCUMENTO:") <= knowledge_module.MAX_SEMANTIC_CHUNKS

        # No chunk for the agent's model: keyword fallback still answers.
        for chunk in chunks:
            chunk.embedding_model = "google/gemini-embedding-2"
        db.commit()
        fallback = asyncio.run(knowledge_module.retrieve_knowledge(db, agent, "topic 3"))
        assert "topic 3" in fallback.text


def test_reindex_single_document(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    agent_id = _setup_agent(client)
    monkeypatch.setattr(agents_router, "PdfReader", _reader_for("A document about warranties."))
    monkeypatch.setattr(knowledge_module, "embed_texts", _fake_embed(3))
    doc = client.post(f"/api/agents/{agent_id}/documents", files={"file": ("a.pdf", b"%PDF-test", "application/pdf")}).json()

    # Change the model, then reindex just this document into the new one.
    client.patch(f"/api/agents/{agent_id}", json={"embedding_model": "qwen/qwen3-embedding-8b"})
    monkeypatch.setattr(knowledge_module, "embed_texts", _fake_embed(4))
    reindexed = client.post(f"/api/agents/{agent_id}/documents/{doc['id']}/reindex")
    assert reindexed.status_code == 200, reindexed.text
    assert reindexed.json()["indexed_model"] == "qwen/qwen3-embedding-8b"

    # Unknown document is a 404, and a provider that returns nothing is a 502.
    # A fresh id, not a variation of the real one: swapping digits leaves an id
    # with none of them unchanged, and the request then finds the document.
    assert client.post(f"/api/agents/{agent_id}/documents/{uuid.uuid4()}/reindex").status_code in (404, 422)
    monkeypatch.setattr(knowledge_module, "embed_texts", AsyncMock(return_value=None))
    assert client.post(f"/api/agents/{agent_id}/documents/{doc['id']}/reindex").status_code == 502


def test_catalog_lists_embedding_models(authenticated_client: TestClient):
    models = authenticated_client.get("/api/catalog/embedding-models").json()
    assert "openai/text-embedding-3-small" in [m["id"] for m in models]
    assert all(m["context_window"] >= 2048 for m in models)
    available = authenticated_client.get("/api/catalog/available").json()
    assert "openai/text-embedding-3-small" in available["embedding"]
