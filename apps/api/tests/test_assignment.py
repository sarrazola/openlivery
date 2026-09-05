from fastapi.testclient import TestClient

from conftest import customer_conversation


def _portal_with_two_people(client: TestClient):
    customer = client.post(
        "/api/clients",
        json={"name": "Handoff Co", "is_active": True},
    ).json()
    for name, email in (("Ana", "ana@handoff.com"), ("Pablo", "pablo@handoff.com")):
        client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": name, "email": email, "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "name": "Host", "instructions": "", "personality": "", "model": "", "is_active": True},
    ).json()
    conversation_id = customer_conversation(client, agent["id"])["id"]
    return customer["portal_slug"], conversation_id


def _login(client: TestClient, slug: str, email: str):
    session = client.post(f"/api/portal/{slug}/login", json={"email": email, "password": "secure-portal"}).json()
    assert session["user_name"]
    return session["user_id"]


def test_taking_over_assigns_and_the_thread_narrates_handoffs(authenticated_client: TestClient):
    client = authenticated_client
    slug, cid = _portal_with_two_people(client)
    base = f"/api/portal/{slug}/conversations"
    ana = _login(client, slug, "ana@handoff.com")

    members = client.get(f"/api/portal/{slug}/members").json()
    pablo = next(m["id"] for m in members if m["name"] == "Pablo")
    assert {m["name"] for m in members} == {"Ana", "Pablo"}

    # Taking over hands the conversation to the person who did it.
    taken = client.patch(f"{base}/{cid}/mode", json={"mode": "human"}).json()
    assert taken["assignee_id"] == ana and taken["assignee_name"] == "Ana"
    summary = client.get(f"{base}/summary").json()
    assert summary["mine"] == 1 and summary["unassigned"] == 0
    assert [row["id"] for row in client.get(f"{base}?assignee=me").json()] == [cid]
    assert client.get(f"{base}?assignee=none").json() == []

    # Transfer to Pablo.
    moved = client.post(f"{base}/{cid}/assignment", json={"assignee_id": pablo}).json()
    assert moved["assignee_name"] == "Pablo"
    assert moved["messages"][-1]["activity"] == {"event": "transferred", "assignee": "Pablo", "from": "Ana"}
    assert moved["messages"][-1]["sender_name"] == "Ana"
    assert client.get(f"{base}?assignee=me").json() == []
    assert client.get(f"{base}/summary").json()["mine"] == 0

    # Pablo signs in: it is his now, and his replies carry his id.
    pablo_id = _login(client, slug, "pablo@handoff.com")
    assert pablo_id == pablo
    assert [row["assignee_name"] for row in client.get(f"{base}?assignee=me").json()] == ["Pablo"]
    replied = client.post(f"{base}/{cid}/reply", json={"content": "On it"}).json()
    assert replied["messages"][-1]["sender_name"] == "Pablo"

    # A conversation is never without an owner: letting go means the AI takes it.
    assert client.post(f"{base}/{cid}/assignment", json={"assignee_id": None}).status_code == 422
    assert client.get(f"{base}/{cid}").json()["assignee_name"] == "Pablo"
    # Assigning to yourself what you already hold changes nothing and adds no line.
    before = client.get(f"{base}/{cid}").json()
    again = client.post(f"{base}/{cid}/assignment", json={"assignee_id": pablo}).json()
    assert len(again["messages"]) == len(before["messages"])

    # Handing back to the AI releases it.
    back = client.patch(f"{base}/{cid}/mode", json={"mode": "ai"}).json()
    assert back["assignee_id"] is None
    assert client.post(f"{base}/{cid}/assignment", json={"assignee_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_assigning_a_person_takes_the_conversation_from_the_ai(authenticated_client: TestClient):
    client = authenticated_client
    slug, cid = _portal_with_two_people(client)
    base = f"/api/portal/{slug}/conversations"
    _login(client, slug, "ana@handoff.com")
    pablo = next(m["id"] for m in client.get(f"/api/portal/{slug}/members").json() if m["name"] == "Pablo")
    assigned = client.post(f"{base}/{cid}/assignment", json={"assignee_id": pablo}).json()
    assert assigned["mode"] == "human" and assigned["assignee_name"] == "Pablo"
    assert assigned["messages"][-1]["activity"] == {"event": "assigned", "assignee": "Pablo"}
