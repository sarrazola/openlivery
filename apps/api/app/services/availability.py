"""When an agent is on duty.

An agent answers while it is active and, when it keeps a schedule, only inside
one of its slots. A slot is ``{"day": 0..6, "start": "HH:MM", "end": "HH:MM"}``
with Monday as 0, read in the client's timezone; ``end`` may be ``"24:00"`` for
the end of the day. Outside the schedule an inbound message is kept and nobody
answers, like an inactive agent, except that the agent comes back on by itself.
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import Agent, now_utc

DAYS = range(7)


def minutes_of(value: str) -> int:
    """"HH:MM" as minutes from midnight; raises ValueError when malformed."""
    hours, _, minutes = str(value).partition(":")
    if not (hours.isdigit() and minutes.isdigit() and len(minutes) == 2):
        raise ValueError(f"Invalid time: {value!r}")
    total = int(hours) * 60 + int(minutes)
    if int(minutes) > 59 or total > 24 * 60:
        raise ValueError(f"Invalid time: {value!r}")
    return total


def check_slots(slots: list) -> list[dict]:
    """Normalize a schedule: every slot has a known weekday and a start before its end."""
    cleaned = []
    for slot in slots or []:
        if not isinstance(slot, dict):
            raise ValueError("Each schedule slot must be an object")
        day = slot.get("day")
        if not isinstance(day, int) or isinstance(day, bool) or day not in DAYS:
            raise ValueError("The schedule day must be 0 (Monday) to 6 (Sunday)")
        start, end = minutes_of(slot.get("start", "")), minutes_of(slot.get("end", ""))
        if start >= end:
            raise ValueError("A schedule slot must end after it starts")
        cleaned.append({"day": day, "start": f"{start // 60:02d}:{start % 60:02d}", "end": f"{end // 60:02d}:{end % 60:02d}"})
    return cleaned


def on_duty(agent: Agent, now: datetime | None = None) -> bool:
    """True unless the agent keeps a schedule and ``now`` falls outside it."""
    if not agent.schedule_enabled:
        return True
    try:
        zone = ZoneInfo(getattr(agent.client, "timezone", None) or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    local = (now or now_utc()).astimezone(zone)
    minute = local.hour * 60 + local.minute
    for slot in agent.schedule_slots or []:
        try:
            if slot["day"] == local.weekday() and minutes_of(slot["start"]) <= minute < minutes_of(slot["end"]):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def agent_available(agent: Agent, now: datetime | None = None) -> bool:
    """Active and on duty: what every path that answers for the agent checks."""
    return bool(agent.is_active) and on_duty(agent, now)
