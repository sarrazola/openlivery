"""The agency is told where the deployment's mobile app lives, and only when
the deployment says so. The client portal does not carry the links."""

from fastapi.testclient import TestClient


def _portal(client: TestClient):
    customer = client.post("/api/clients", json={"name": "Links Co", "is_active": True}).json()
    client.post(f"/api/clients/{customer['id']}/portal-users", json={"name": "Ana", "email": "ana@links.co", "password": "secure-portal"})
    client.patch(f"/api/clients/{customer['id']}/portal", json={"portal_enabled": True})
    return customer["portal_slug"]


def test_store_links_reach_the_agency_only_when_configured(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "portal_ios_app_url", "", raising=False)
    monkeypatch.setattr(get_settings(), "portal_android_app_url", "", raising=False)
    agency = client.get("/api/agency").json()
    assert agency["ios_app_url"] is None and agency["android_app_url"] is None

    monkeypatch.setattr(get_settings(), "portal_ios_app_url", " https://apps.example/id1 ", raising=False)
    monkeypatch.setattr(get_settings(), "portal_android_app_url", "", raising=False)
    agency = client.get("/api/agency").json()
    assert agency["ios_app_url"] == "https://apps.example/id1"
    assert agency["android_app_url"] is None
    # Every route that returns the agency carries them the same way.
    patched = client.patch("/api/agency", json={"name": "Links Agency"}).json()
    assert patched["name"] == "Links Agency" and patched["ios_app_url"] == "https://apps.example/id1"


def test_portal_public_info_does_not_carry_store_links(authenticated_client: TestClient, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "portal_ios_app_url", "https://apps.example/id1", raising=False)
    slug = _portal(authenticated_client)
    public = authenticated_client.get(f"/api/portal/{slug}").json()
    assert "ios_app_url" not in public and "android_app_url" not in public
