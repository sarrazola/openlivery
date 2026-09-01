"""Teams: trays of portal users, the strategies that pick who gets the next
conversation, and moving conversations between trays."""

import uuid

from fastapi.testclient import TestClient


def _portal_with_members(client: TestClient, names: list[str], company: str = "Teams Co"):
    customer = client.post(
        "/api/clients",
        json={"name": company, "industry": "", "description": "", "general_context": "", "is_active": True},
    ).json()
    slug = customer["portal_slug"]
    members = []
    for index, name in enumerate(names):
        client.post(
            f"/api/clients/{customer['id']}/portal-users",
            json={"name": name, "email": f"user{index}@{slug}.com", "password": "secure-portal"},
        )
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{slug}/login", json={"email": f"user0@{slug}.com", "password": "secure-portal"})
    members = client.get(f"/api/portal/{slug}/members").json()
    return customer, slug, members


def _conversation(client: TestClient, customer: dict, slug: str, title_hint: str = "hola") -> str:
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Beto", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    conversation = client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    return conversation["id"]


def test_team_crud_and_membership(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, members = _portal_with_members(client, ["Ana", "Beto", "Cami"])
    base = f"/api/portal/{slug}/teams"

    created = client.post(base, json={"name": "Ventas", "description": "Cotizaciones", "strategy": "round_robin", "channels": ["whatsapp"], "member_ids": [members[0]["id"], members[1]["id"]]})
    assert created.status_code == 201, created.text
    team = created.json()
    assert team["name"] == "Ventas" and team["strategy"] == "round_robin"
    assert {m["id"] for m in team["members"]} == {members[0]["id"], members[1]["id"]}

    # Duplicate names are refused; unknown channels too.
    assert client.post(base, json={"name": "Ventas", "member_ids": []}).status_code == 409
    assert client.post(base, json={"name": "Otra", "channels": ["telegram"], "member_ids": []}).status_code == 422

    # Membership converges to what the payload says.
    updated = client.patch(f"{base}/{team['id']}", json={"name": "Ventas", "strategy": "least_busy", "member_ids": [members[2]["id"]]}).json()
    assert updated["strategy"] == "least_busy"
    assert [m["id"] for m in updated["members"]] == [members[2]["id"]]

    # Only one default tray per client.
    second = client.post(base, json={"name": "Soporte", "is_default": True, "member_ids": []}).json()
    third = client.post(base, json={"name": "Urgencias", "is_default": True, "member_ids": []}).json()
    listing = {row["name"]: row for row in client.get(base).json()}
    assert listing["Urgencias"]["is_default"] is True and listing["Soporte"]["is_default"] is False

    assert client.delete(f"{base}/{team['id']}").status_code == 204
    assert "Ventas" not in {row["name"] for row in client.get(base).json()}
    assert second and third


def test_moving_a_conversation_routes_round_robin(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, members = _portal_with_members(client, ["Ana", "Beto", "Cami"], company="Rotation Co")
    base = f"/api/portal/{slug}/teams"
    # Ana (the signed-in mover) is NOT in the tray, so handing a conversation
    # she holds to it releases her and routing picks a member.
    beto, cami = members[1]["id"], members[2]["id"]
    team = client.post(base, json={"name": "Soporte", "member_ids": [beto, cami]}).json()

    first = _conversation(client, customer, slug)

    # An AI-mode conversation moves trays without leaving the AI.
    moved = client.patch(f"/api/portal/{slug}/conversations/{first}/team", json={"team_id": team["id"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["team_id"] == team["id"] and moved.json()["team_name"] == "Soporte"
    assert moved.json()["mode"] == "ai" and moved.json()["assignee_id"] is None

    def taken_and_moved(conversation_id: str) -> dict:
        client.patch(f"/api/portal/{slug}/conversations/{conversation_id}/mode", json={"mode": "human"})
        return client.patch(
            f"/api/portal/{slug}/conversations/{conversation_id}/team", json={"team_id": team["id"]}
        ).json()

    second = taken_and_moved(_conversation(client, customer, slug))
    third = taken_and_moved(_conversation(client, customer, slug))
    assert second["assignee_id"] in {beto, cami}
    assert third["assignee_id"] in {beto, cami}
    assert third["assignee_id"] != second["assignee_id"], "round robin must rotate"

    # The activity trail narrates the tray move and the hand-over.
    events = [m["activity"]["event"] for m in third["messages"] if m.get("kind") == "activity" and m.get("activity")]
    assert "team_assigned" in events and ("assigned" in events or "transferred" in events)


def test_away_members_are_skipped_and_empty_teams_leave_unassigned(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, members = _portal_with_members(client, ["Ana", "Beto"], company="Presence Co")
    base = f"/api/portal/{slug}/teams"
    ana, beto = members[0]["id"], members[1]["id"]

    # Ana (signed in) marks herself away; the tray holds only her.
    me = client.patch(f"/api/portal/{slug}/me", json={"availability": "away"})
    assert me.status_code == 200 and me.json()["availability"] == "away"
    lonely = client.post(base, json={"name": "Solo", "member_ids": [ana]}).json()

    # Beto signs in, takes a conversation and drops it into Ana's tray:
    # nobody eligible, so it waits unassigned.
    client.post(f"/api/portal/{slug}/login", json={"email": f"user1@{slug}.com", "password": "secure-portal"})
    conversation = _conversation(client, customer, slug)
    client.patch(f"/api/portal/{slug}/conversations/{conversation}/mode", json={"mode": "human"})
    waiting = client.patch(f"/api/portal/{slug}/conversations/{conversation}/team", json={"team_id": lonely["id"]}).json()
    assert waiting["assignee_id"] is None and waiting["team_id"] == lonely["id"]

    # The tray counters see it, and the inbox can filter by tray.
    listing = {row["name"]: row for row in client.get(base).json()}
    assert listing["Solo"]["unassigned_count"] == 1
    rows = client.get(f"/api/portal/{slug}/conversations?team={lonely['id']}").json()
    assert [row["id"] for row in rows] == [conversation]

    # Once Ana is back online, a fresh drop into her tray reaches her.
    client.post(f"/api/portal/{slug}/login", json={"email": f"user0@{slug}.com", "password": "secure-portal"})
    client.patch(f"/api/portal/{slug}/me", json={"availability": "online"})
    client.post(f"/api/portal/{slug}/login", json={"email": f"user1@{slug}.com", "password": "secure-portal"})
    another = _conversation(client, customer, slug)
    client.patch(f"/api/portal/{slug}/conversations/{another}/mode", json={"mode": "human"})
    routed = client.patch(f"/api/portal/{slug}/conversations/{another}/team", json={"team_id": lonely["id"]}).json()
    assert routed["assignee_id"] == ana
    assert beto


def test_escalation_rules_replace_and_validate(authenticated_client: TestClient):
    client = authenticated_client
    customer, slug, members = _portal_with_members(client, ["Ana"], company="Rules Co")
    team = client.post(f"/api/portal/{slug}/teams", json={"name": "Ventas", "member_ids": [members[0]["id"]]}).json()
    client.put("/api/providers/openai", json={"api_key": "secret"})
    agent = client.post(
        "/api/agents",
        json={"client_id": customer["id"], "provider": "openai", "model": "gpt-4.1-mini", "name": "Beto", "description": "", "instructions": "", "personality": "", "is_active": True},
    ).json()
    base = f"/api/agents/{agent['id']}/escalation-rules"

    # A rule needs exactly one destination, and it must belong to the client.
    assert client.put(base, json=[{"condition": "cotizaciones"}]).status_code == 422
    assert client.put(base, json=[{"condition": "x", "team_id": team["id"], "assignee_id": members[0]["id"]}]).status_code == 422
    assert client.put(base, json=[{"condition": "x", "team_id": str(uuid.uuid4())}]).status_code == 422

    saved = client.put(base, json=[
        {"condition": "Preguntas por cotizaciones o precios corporativos", "team_id": team["id"]},
        {"condition": "Reclamos de facturacion", "assignee_id": members[0]["id"], "is_active": False},
    ])
    assert saved.status_code == 200, saved.text
    rules = saved.json()
    assert [rule["position"] for rule in rules] == [0, 1]
    assert rules[0]["team_name"] == "Ventas" and rules[0]["broken"] is False
    assert rules[1]["assignee_name"] == "Ana" and rules[1]["is_active"] is False

    # Replacing converges to the new list.
    saved = client.put(base, json=[{"condition": "Solo esta", "team_id": team["id"]}]).json()
    assert len(saved) == 1
    assert client.get(base).json() == saved

    # Deleting the destination team leaves the rule visibly broken.
    client.delete(f"/api/portal/{slug}/teams/{team['id']}")
    assert client.get(base).json()[0]["broken"] is True
