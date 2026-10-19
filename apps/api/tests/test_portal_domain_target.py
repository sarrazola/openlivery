"""The client page says where a portal domain's CNAME must point, when the
deployment says so."""

from fastapi.testclient import TestClient


def test_cname_target_follows_the_setting(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    customer = client.post("/api/clients", json={"name": "Target Co", "is_active": True}).json()
    assert client.get(f"/api/clients/{customer['id']}/domain").json()["cname_target"] is None

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "portal_domain_cname_target", " app.agency.example ", raising=False)
    assert client.get(f"/api/clients/{customer['id']}/domain").json()["cname_target"] == "app.agency.example"
    saved = client.put(f"/api/clients/{customer['id']}/domain", json={"domain": "chat.brand.example"}).json()
    assert saved["cname_target"] == "app.agency.example"
