"""The portal tells its people where the deployment's mobile app lives, and
only when the deployment says so."""

from fastapi.testclient import TestClient


def _portal(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Links Co", "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@links.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    return customer["portal_slug"]


def test_store_links_appear_only_when_configured(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    slug = _portal(client)
    public = client.get(f"/api/portal/{slug}").json()
    assert public["ios_app_url"] is None and public["android_app_url"] is None

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "portal_ios_app_url", " https://apps.example/id1 ", raising=False)
    monkeypatch.setattr(get_settings(), "portal_android_app_url", "", raising=False)
    public = client.get(f"/api/portal/{slug}").json()
    assert public["ios_app_url"] == "https://apps.example/id1"
    assert public["android_app_url"] is None
