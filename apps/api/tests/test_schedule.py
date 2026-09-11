"""Opening hours: what the agent is told, and when it must stay quiet."""

from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.services import schedule

TZ = ZoneInfo("America/Mexico_City")
SPLIT = [
    [["09:00", "14:00"], ["16:00", "20:00"]],  # Monday
    [["09:00", "14:00"], ["16:00", "20:00"]],
    [["09:00", "18:00"]],
    [["09:00", "18:00"]],
    [["09:00", "18:00"]],
    [["10:00", "14:00"]],                      # Saturday
    [],                                        # Sunday, closed
]


def _agent(mode: str, days=None, tools=(), note=""):
    return SimpleNamespace(
        business_hours={"mode": mode, "days": days or [[]] * 7, "note": note},
        timezone="America/Mexico_City",
        tools=[SimpleNamespace(enabled=enabled) for enabled in tools],
    )


def test_split_shift_closes_for_lunch():
    agent = _agent("custom", SPLIT)
    assert schedule.is_open(agent, datetime(2026, 8, 25, 10, 0, tzinfo=TZ))
    assert not schedule.is_open(agent, datetime(2026, 8, 25, 15, 0, tzinfo=TZ))
    assert schedule.is_open(agent, datetime(2026, 8, 25, 17, 0, tzinfo=TZ))


def test_a_closed_day_offers_no_slots():
    agent = _agent("custom", SPLIT)
    assert schedule.slots_for(agent, date(2026, 8, 30)) == []
    assert [(slot.start, slot.end) for slot in schedule.slots_for(agent, date(2026, 8, 25))] == [
        (time(9, 0), time(14, 0)),
        (time(16, 0), time(20, 0)),
    ]


def test_next_opening_skips_the_closed_sunday():
    upcoming = schedule.next_opening(_agent("custom", SPLIT), datetime(2026, 8, 30, 12, 0, tzinfo=TZ))
    assert (upcoming.date(), upcoming.hour) == (date(2026, 8, 31), 9)


def test_always_open_never_reports_closed():
    agent = _agent("always")
    when = datetime(2026, 8, 30, 3, 0, tzinfo=TZ)
    assert schedule.is_open(agent, when)
    assert "OPEN right now" in schedule.prompt_block(agent, when, lang="en")


def test_closed_state_tells_the_agent_when_it_reopens():
    block = schedule.prompt_block(_agent("custom", SPLIT), datetime(2026, 8, 25, 22, 30, tzinfo=TZ), lang="en")
    assert "CLOSED right now" in block
    assert "09:00" in block


def test_hours_are_written_in_the_prompt_language():
    when = datetime(2026, 8, 25, 22, 30, tzinfo=TZ)
    spanish = schedule.prompt_block(_agent("custom", SPLIT), when, lang="es")
    assert "CERRADO ahora mismo" in spanish and "Domingo: cerrado" in spanish
    english = schedule.prompt_block(_agent("custom", SPLIT), when, lang="en")
    assert "CLOSED right now" in english and "Sunday: closed" in english


def test_without_hours_or_tools_the_prompt_says_nothing():
    assert schedule.prompt_block(_agent("off"), datetime(2026, 8, 25, 10, 0, tzinfo=TZ)) is None


def test_without_hours_but_with_a_tool_that_knows_them():
    """"Not written here" must never break the tool that does know the hours:
    the agent is told to look them up instead of denying it has any."""
    block = schedule.prompt_block(
        _agent("off"), datetime(2026, 8, 25, 10, 0, tzinfo=TZ), has_tool_source=True, lang="en"
    )
    assert block is not None
    assert "your tools" in block and "never say the business has none" in block


def test_the_prompt_carries_the_hours_and_the_note(authenticated_client: TestClient):
    client = authenticated_client
    customer = client.post(
        "/api/clients",
        json={"name": "Bakery", "industry": "restaurants_food", "business_type": "restaurant", "is_active": True},
    )
    assert customer.status_code == 201, customer.text
    customer = customer.json()
    client.put("/api/providers/openai", json={"api_key": "sk-test"})
    agent = client.post(
        "/api/agents",
        json={
            "client_id": customer["id"],
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "timezone": "America/Mexico_City",
            "prompt_language": "en",
            "name": "Pan",
            "instructions": "Take orders.",
            "personality": "Warm",
            "is_active": True,
            "business_hours": {"mode": "custom", "days": SPLIT, "note": "Closed on public holidays."},
        },
    )
    assert agent.status_code == 201, agent.text
    assert agent.json()["business_hours"]["mode"] == "custom"

    prompt = client.get(f"/api/agents/{agent.json()['id']}/prompt").json()["prompt"]
    assert "## Opening hours" in prompt
    assert "Monday: 09:00–14:00, 16:00–20:00" in prompt
    assert "Closed on public holidays." in prompt

    # Switching it off takes the section out again.
    client.patch(f"/api/agents/{agent.json()['id']}", json={"business_hours": {"mode": "off"}})
    assert "## Opening hours" not in client.get(f"/api/agents/{agent.json()['id']}/prompt").json()["prompt"]
