from fastapi.testclient import TestClient


def _portal(client: TestClient, name: str, email: str):
    customer = client.post(
        "/api/clients",
        json={"name": name, "is_active": True},
    ).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": email, "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    client.post(f"/api/portal/{customer['portal_slug']}/login", json={"email": email, "password": "secure-portal"})
    return customer


def test_saved_replies_are_managed_per_business(authenticated_client: TestClient):
    client = authenticated_client
    slug = _portal(client, "Canned Co", "ana@canned.co")["portal_slug"]
    base = f"/api/portal/{slug}/canned-responses"

    assert client.get(base).json() == []
    bad = client.post(base, json={"shortcut": "Bad Name", "content": "x"})
    assert bad.status_code == 422

    created = client.post(base, json={"shortcut": "saludo", "content": "Hola {contact_name}, soy {my_name}."})
    assert created.status_code == 201, created.text
    saved = created.json()
    assert saved["shortcut"] == "saludo" and "{contact_name}" in saved["content"]
    assert client.post(base, json={"shortcut": "saludo", "content": "otro"}).status_code == 409

    client.post(base, json={"shortcut": "direccion", "content": "Estamos en la carrera 1 # 1-23."})
    assert [r["shortcut"] for r in client.get(base).json()] == ["direccion", "saludo"]

    edited = client.patch(f"{base}/{saved['id']}", json={"content": "Hola {contact_name}!"})
    assert edited.status_code == 200 and edited.json()["content"] == "Hola {contact_name}!"
    renamed = client.patch(f"{base}/{saved['id']}", json={"shortcut": "bienvenida"})
    assert renamed.status_code == 200 and renamed.json()["shortcut"] == "bienvenida"

    assert client.delete(f"{base}/{saved['id']}").status_code == 204
    assert [r["shortcut"] for r in client.get(base).json()] == ["direccion"]


def test_saved_replies_stay_within_their_portal(authenticated_client: TestClient):
    client = authenticated_client
    first = _portal(client, "First Co", "ana@first.co")
    first_base = f"/api/portal/{first['portal_slug']}/canned-responses"
    saved = client.post(first_base, json={"shortcut": "saludo", "content": "Hola!"}).json()

    second = _portal(client, "Second Co", "ana@second.co")
    second_base = f"/api/portal/{second['portal_slug']}/canned-responses"
    assert client.get(second_base).json() == []
    # The same shortcut is free in another portal, and foreign ids are invisible.
    assert client.post(second_base, json={"shortcut": "saludo", "content": "Hola!"}).status_code == 201
    assert client.delete(f"{second_base}/{saved['id']}").status_code == 404
