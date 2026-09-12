"""First-run setup is exclusive, retryable, and safe for existing data."""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.config import Settings
from app.main import app
from app.models import Agency, User
from app.routers import auth
from conftest import TestingSession, login_legacy_owner, test_engine


def owner(index):
    return {
        "agency_name": f"Studio {index}", "name": f"Owner {index}",
        "email": f"owner{index}@example.com", "password": "safe-test-password",
    }


def test_removed_registration_setting_cannot_reopen_setup(client, monkeypatch):
    monkeypatch.setenv("ALLOW_MULTI_AGENCY", "true")
    settings = Settings(_env_file=None)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    assert client.post("/api/auth/register", json=owner(1)).status_code == 201
    assert client.get("/api/auth/status").json() == {"needs_setup": False, "registration_open": False}
    assert client.post("/api/auth/register", json=owner(2)).status_code == 403


def test_simultaneous_first_registrations_create_exactly_one_owner(client):
    def register(index):
        with TestClient(app) as requester:
            return requester.post("/api/auth/register", json=owner(index)).status_code

    # Hold writes while both requests reach the database. Reads remain allowed,
    # so a check-then-insert implementation would let both see an empty table.
    # Observe the actual database waiters rather than relying on request timing.
    with test_engine.connect() as blocker, ThreadPoolExecutor(max_workers=2) as executor:
        blocker.execute(text("LOCK TABLE agencies IN EXCLUSIVE MODE"))
        attempts = [executor.submit(register, index) for index in (1, 2)]
        try:
            deadline = monotonic() + 10
            while monotonic() < deadline:
                waiters = blocker.scalar(text("""
                    SELECT count(*) FROM pg_locks
                    WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
                      AND relation = 'agencies'::regclass AND NOT granted
                """))
                if waiters == 2:
                    break
                sleep(0.01)
            else:
                pytest.fail("Both setup requests must reach the database before releasing writes")
        finally:
            blocker.rollback()
        assert sorted(attempt.result(timeout=10) for attempt in attempts) == [201, 403]

    with TestingSession() as db:
        assert db.scalar(select(func.count()).select_from(Agency)) == 1
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_failed_setup_releases_lock_and_can_be_retried(client, monkeypatch):
    def fail_hash(_password):
        raise RuntimeError("Simulated setup failure")

    with monkeypatch.context() as patch:
        patch.setattr(auth, "hash_password", fail_hash)
        with pytest.raises(RuntimeError, match="Simulated setup failure"):
            client.post("/api/auth/register", json=owner(1))
    assert client.get("/api/auth/status").json() == {"needs_setup": True, "registration_open": True}
    assert client.post("/api/auth/register", json=owner(1)).status_code == 201


def test_existing_owners_keep_login_and_data_after_registration_closes(client):
    assert client.post("/api/auth/register", json=owner(1)).status_code == 201
    original_client = client.post("/api/clients", json={"name": "Original client"}).json()
    legacy = login_legacy_owner(client)
    assert client.get("/api/auth/me").json()["id"] == legacy["id"]
    assert client.get(f"/api/clients/{original_client['id']}").status_code == 404
    assert client.post("/api/auth/register", json=owner(3)).status_code == 403
    assert client.get("/api/auth/status").json()["registration_open"] is False
    assert client.post("/api/auth/login", json=owner(1)).status_code == 200
    assert client.get(f"/api/clients/{original_client['id']}").status_code == 200
    with TestingSession() as db:
        assert db.scalar(select(func.count()).select_from(Agency)) == 2


def test_one_agency_can_create_multiple_clients(authenticated_client):
    first = authenticated_client.post("/api/clients", json={"name": "First client"})
    second = authenticated_client.post("/api/clients", json={"name": "Second client"})
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert authenticated_client.get("/api/auth/status").json()["registration_open"] is False
    with TestingSession() as db:
        assert db.scalar(select(func.count()).select_from(Agency)) == 1
