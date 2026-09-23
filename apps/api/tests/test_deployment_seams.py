"""The points where a deployment plugs in without editing this code.

Each is a registry with a documented shape: ``register_credential_fallback`` in
services.providers, ``register_usage_hook`` in services.usage, and
``register_provider`` in services.notifications (tested with the mobile push).
A deployment that relies on one is broken by a change to its shape, so the
shapes are pinned here.
"""

import inspect

from fastapi.testclient import TestClient

from sqlalchemy import select

from app.models import Agency
from app.services import providers, usage
from app.services.ai import Completion
from tests.conftest import TestingSession


def _agency_id(client: TestClient):
    with TestingSession() as db:
        return db.scalar(select(Agency.id))


def test_a_stored_key_wins_and_the_fallback_answers_only_when_there_is_none(authenticated_client: TestClient):
    agency_id = _agency_id(authenticated_client)
    asked = []

    def lend(db, agency, provider):
        asked.append((agency, provider))
        return ("https://lender.example/v1", "lent-key")

    providers.register_credential_fallback(lend)
    try:
        with TestingSession() as db:
            assert providers.credential_source(db, agency_id, "openrouter") == "deployment"
            assert providers.resolve_provider_credentials(db, agency_id, "openrouter") == ("https://lender.example/v1", "lent-key")
            assert providers.credential_source(db, agency_id, "nope") == "none"

        authenticated_client.put("/api/providers/openrouter", json={"api_key": "sk-own-key"})
        asked.clear()
        with TestingSession() as db:
            assert providers.credential_source(db, agency_id, "openrouter") == "agency"
            base_url, key = providers.resolve_provider_credentials(db, agency_id, "openrouter")
            assert key == "sk-own-key" and base_url == providers.base_url_for("openrouter")
        assert asked == [], "the fallback is not consulted when the agency holds a key"
    finally:
        providers.register_credential_fallback(None)


def test_the_listing_reports_a_lent_key_as_configured_and_says_where_it_comes_from(authenticated_client: TestClient):
    (row,) = [r for r in authenticated_client.get("/api/providers").json() if r["provider"] == "openrouter"]
    assert row["configured"] is False and row["source"] == "none"

    providers.register_credential_fallback(lambda db, agency, provider: ("https://lender.example/v1", "lent-key"))
    try:
        (row,) = [r for r in authenticated_client.get("/api/providers").json() if r["provider"] == "openrouter"]
        assert row["configured"] is True and row["source"] == "deployment" and row["api_key_masked"] == ""

        authenticated_client.put("/api/providers/openrouter", json={"api_key": "sk-own-key"})
        (row,) = [r for r in authenticated_client.get("/api/providers").json() if r["provider"] == "openrouter"]
        assert row["configured"] is True and row["source"] == "agency" and row["api_key_masked"]
    finally:
        providers.register_credential_fallback(None)


def test_the_listing_asks_the_probe_when_the_lender_gives_one(authenticated_client: TestClient):
    """A lender may stop lending (an allowance ran out) while still able to produce the key;
    the listing must say so instead of letting the UI promise a reply that would be refused."""
    providers.register_credential_fallback(
        lambda db, agency, provider: ("https://lender.example/v1", "lent-key"),
        available=lambda db, agency, provider: False,
    )
    try:
        (row,) = [r for r in authenticated_client.get("/api/providers").json() if r["provider"] == "openrouter"]
        assert row["configured"] is False and row["source"] == "none"
    finally:
        providers.register_credential_fallback(None)


def test_usage_hooks_see_every_record_and_cannot_fail_the_reply(authenticated_client: TestClient):
    agency_id = _agency_id(authenticated_client)
    seen = []

    def note(db, record, completion, *, conversation=None, message=None):
        seen.append((record.id, record.input_tokens, conversation, message))

    def broken(db, record, completion, **context):
        raise RuntimeError("a hook that misbehaves")

    usage.register_usage_hook(note)
    usage.register_usage_hook(broken)
    usage.register_usage_hook(note)  # registering twice does not double it
    try:
        with TestingSession() as db:
            record = usage.record_usage(db, agency_id, None, "openrouter", "openai/gpt-5.6-luna",
                                        Completion(text="", input_tokens=7, output_tokens=3))
            assert record is not None
            assert seen == [(record.id, 7, None, None)]
            assert usage.record_usage(db, agency_id, None, "openrouter", "m", Completion(text="", input_tokens=0, output_tokens=0)) is None
            assert len(seen) == 1, "no record, no hook"
    finally:
        usage._usage_hooks[:] = [h for h in usage._usage_hooks if h not in (note, broken)]


def _params(function) -> list[str]:
    return [p.name for p in inspect.signature(function).parameters.values()]


def test_the_shapes_a_deployment_relies_on():
    assert _params(providers.register_credential_fallback) == ["fallback", "available"]
    assert _params(providers.resolve_provider_credentials) == ["db", "agency_id", "provider"]
    assert _params(providers.credential_source) == ["db", "agency_id", "provider"]
    assert _params(usage.register_usage_hook) == ["hook"]
    assert _params(usage.record_usage) == ["db", "agency_id", "agent_id", "provider", "model", "completion", "conversation", "message"]
