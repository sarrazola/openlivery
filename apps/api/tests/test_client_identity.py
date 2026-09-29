from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.routers import conversations as conversations_router
from app.services import ai as ai_service


def test_industry_catalog_lists_types_with_both_labels(authenticated_client: TestClient):
    catalog = authenticated_client.get("/api/industries")
    assert catalog.status_code == 200
    finance = next(item for item in catalog.json() if item["code"] == "finance_insurance")
    assert finance["label"] == {"en": "Finance & insurance", "es": "Finanzas y seguros"}
    codes = [kind["code"] for kind in finance["types"]]
    assert "accounting_tax" in codes
    assert codes[-1] == "other"
    assert all(item["types"][-1]["code"] == "other" for item in catalog.json())


def test_client_industry_and_type_are_validated_against_the_catalog(authenticated_client: TestClient):
    client = authenticated_client
    created = client.post("/api/clients", json={"name": "FinancialCoach", "industry": "finance_insurance", "business_type": "accounting_tax"})
    assert created.status_code == 201, created.text
    assert created.json()["business_type"] == "accounting_tax"

    unknown = client.post("/api/clients", json={"name": "X", "industry": "space_mining"})
    assert unknown.status_code == 422
    mismatched = client.post("/api/clients", json={"name": "X", "industry": "education", "business_type": "accounting_tax"})
    assert mismatched.status_code == 422
    orphan_type = client.post("/api/clients", json={"name": "X", "business_type": "school"})
    assert orphan_type.status_code == 422

    # Moving to another industry drops a type that no longer belongs to it.
    moved = client.patch(f"/api/clients/{created.json()['id']}", json={"industry": "education"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["industry"] == "education"
    assert moved.json()["business_type"] == ""


def test_prompt_names_the_business_type_and_previews_without_knowledge(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "FinancialCoach", "industry": "finance_insurance", "business_type": "accounting_tax"}).json()
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini", "name": "Ramiro", "instructions": "Book tax appointments.", "is_active": True},
    ).json()

    preview = client.get(f"/api/agents/{agent['id']}/prompt")
    assert preview.status_code == 200
    prompt = preview.json()["prompt"]
    assert prompt.startswith("# Ramiro, asistente de IA de FinancialCoach\n- **Nombre:** Ramiro\n- **Negocio:** FinancialCoach\n- **Sector:** Contabilidad / impuestos\nFecha y hora actual")
    assert "## Tu trabajo\nBook tax appointments." in prompt
    assert "## Conocimiento" not in prompt

    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    fake_completion = AsyncMock(return_value=ai_service.Completion(text="ok"))
    monkeypatch.setattr(conversations_router, "run_completion", fake_completion)
    assert client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Hola"}).status_code == 200
    sent = fake_completion.await_args.args[4][0]["content"]
    assert "- **Sector:** Contabilidad / impuestos" in sent


def test_other_says_nothing_about_the_business(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Acme", "industry": "other", "business_type": "other"}).json()
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Bot", "is_active": True}).json()
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert "\n- **Nombre:** Bot\n- **Negocio:** Acme\nFecha y hora actual" in prompt
    assert "Sector" not in prompt


def test_other_with_own_words_names_them_and_a_known_type_wins(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Acme", "industry": "finance_insurance", "business_type": "other", "business_custom": "Casa de cambio"}).json()
    assert customer["business_custom"] == "Casa de cambio"
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Bot", "is_active": True}).json()
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert "\n- **Negocio:** Acme\n- **Sector:** Casa de cambio\n" in prompt

    client.patch(f"/api/clients/{customer['id']}", json={"business_type": "insurance"})
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert "- **Sector:** Seguros\n" in prompt


def test_prompt_headings_follow_the_agent_language_and_keep_the_operator_text(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "FinancialCoach", "industry": "finance_insurance", "business_type": "accounting_tax"}).json()
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"], "name": "Ramiro", "prompt_language": "en", "is_active": True,
            "instructions": "Agenda citas.", "brief_summary": "Contadores en Bogotá", "brief_donts": "Nunca des cifras sin verificar", "personality": "Cálido",
        },
    ).json()
    assert agent["prompt_language"] == "en"
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert prompt.startswith("# Ramiro, AI assistant for FinancialCoach\n- **Name:** Ramiro\n- **Business:** FinancialCoach\n- **Industry:** Accounting / tax\n")
    assert "## Your job\nAgenda citas." in prompt
    assert "## The business\n- **What it does:** Contadores en Bogotá" in prompt
    assert "## Rules\n### Never\n- Never invent or assume facts" in prompt
    # The operator's own "never" lines follow the last base rule.
    assert "A hyphen inside a compound word is fine.\nNunca des cifras sin verificar" in prompt
    assert "### Always" not in prompt
    assert "## Tone\nCálido" in prompt
    assert "## Knowledge" not in prompt

    assert client.post("/api/agents", json={"client_id": customer["id"], "name": "X", "prompt_language": "fr"}).status_code == 422


def test_empty_job_and_tone_are_not_sent(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Acme"}).json()
    agent = client.post("/api/agents", json={"client_id": customer["id"], "name": "Bot", "is_active": True}).json()
    prompt = client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert "## Tu trabajo" not in prompt and "## Tono" not in prompt and "### Siempre" not in prompt
    assert "## Reglas\n### Nunca\n- Nunca inventes ni supongas datos" in prompt


def test_the_client_timezone_is_validated_and_reaches_every_agent(authenticated_client: TestClient):
    client = authenticated_client
    assert client.post("/api/clients", json={"name": "Nowhere", "timezone": "Mars/Olympus"}).status_code == 422
    customer = client.post("/api/clients", json={"name": "Bogota Co", "timezone": "America/Bogota"}).json()
    assert customer["timezone"] == "America/Bogota"
    client.put("/api/providers/openrouter", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openrouter", "model": "gpt-4.1-mini", "name": "Ramiro", "instructions": "x", "is_active": True},
    ).json()
    assert "timezone" not in agent
    assert "America/Bogota" in client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]

    # Changing it on the client changes what the agent is told; blank means UTC.
    assert client.patch(f"/api/clients/{customer['id']}", json={"timezone": "Europe/Madrid"}).json()["timezone"] == "Europe/Madrid"
    assert "Europe/Madrid" in client.get(f"/api/agents/{agent['id']}/prompt").json()["prompt"]
    assert client.patch(f"/api/clients/{customer['id']}", json={"timezone": "nope"}).status_code == 422
    assert client.patch(f"/api/clients/{customer['id']}", json={"timezone": ""}).json()["timezone"] == "UTC"
