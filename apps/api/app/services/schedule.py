"""Opening hours: is the business open right now, and when does it open next.

The model should never be asked to work out whether 22:40 falls inside
"09:00-14:00, 16:00-20:00". We compute it and tell it plainly, because a wrong
answer here means promising a customer attention that nobody will give.

Three modes. ``off`` is the default and means *the hours are not written here*,
which is not the same as *this business has no hours*: when the agent has a
tool that can look them up, the prompt says so instead of going quiet, or the
agent would answer "I don't have the hours" while holding a tool that knows
them. ``always`` is a business that never closes. ``custom`` is a weekly
schedule with up to three ranges a day, so a lunch break is expressible.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import Agent

# Sentences the model reads. Localized like the rest of the prompt scaffolding;
# {} placeholders are filled below.
_TEXT = {
    "es": {
        "days": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "closed": "cerrado",
        "always": "- Todos los días, las 24 horas.",
        "always_state": (
            "ESTADO: ABIERTO ahora mismo. Este negocio nunca cierra, así que no digas que "
            "está cerrado ni pospongas la atención a otro momento."
        ),
        "tool_only": (
            "- No está escrito aquí, pero tus herramientas sí pueden consultarlo.\n\n"
            "Si preguntan por el horario o si el negocio está abierto, búscalo con tus "
            "herramientas y responde con lo que devuelvan. Nunca inventes un horario ni digas "
            "que el negocio no tiene horario. Si la herramienta no lo devuelve, di solamente "
            "que no lo tienes a la mano en este momento."
        ),
        "open_now": "ESTADO: ABIERTO ahora mismo.",
        "closed_now": "ESTADO: CERRADO ahora mismo.",
        "reopens_today": " Vuelve a abrir hoy a las {time}.",
        "reopens_day": " Vuelve a abrir el {day} a las {time}.",
        "rules": (
            "Si está cerrado, dilo con claridad y no prometas atención inmediata ni confirmes un "
            "servicio como si alguien fuera a atenderlo en ese momento. Puedes tomar los datos y "
            "avisar que se atenderá al abrir. Nunca inventes un horario distinto al de arriba."
        ),
        "note": "Nota del negocio sobre el horario: {note}",
    },
    "en": {
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "closed": "closed",
        "always": "- Every day, around the clock.",
        "always_state": (
            "STATUS: OPEN right now. This business never closes, so do not say it is closed or "
            "put the customer off until later."
        ),
        "tool_only": (
            "- Not written here, but your tools can look them up.\n\n"
            "If someone asks about the hours or whether the business is open, look it up with "
            "your tools and answer with what they return. Never invent hours and never say the "
            "business has none. If the tool returns nothing, just say you do not have them at "
            "hand right now."
        ),
        "open_now": "STATUS: OPEN right now.",
        "closed_now": "STATUS: CLOSED right now.",
        "reopens_today": " It opens again today at {time}.",
        "reopens_day": " It opens again on {day} at {time}.",
        "rules": (
            "When it is closed, say so plainly: do not promise immediate attention or confirm a "
            "service as if someone were about to handle it. You can take their details and say "
            "they will be attended when it opens. Never invent hours other than the ones above."
        ),
        "note": "The business's note about the hours: {note}",
    },
}

# Used when an agent has no schedule of its own.
DEFAULT_RANGES = [("09:00", "18:00")] * 5 + [[], []]


@dataclass
class Slot:
    start: time
    end: time


def _text(lang: str) -> dict:
    return _TEXT.get(lang, _TEXT["es"])


def zone_for(agent: Agent) -> ZoneInfo:
    try:
        return ZoneInfo((agent.timezone or "UTC").strip() or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _parse_time(value: str) -> time | None:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


def mode_of(agent: Agent) -> str:
    """One of: "off" (not written here), "always" (24/7), "custom" (weekly)."""
    hours = agent.business_hours or {}
    mode = hours.get("mode")
    return mode if mode in ("off", "always", "custom") else "off"


def is_configured(agent: Agent) -> bool:
    return mode_of(agent) != "off"


def slots_for(agent: Agent, when: date) -> list[Slot]:
    """Opening ranges for one calendar day, in the agent's timezone."""
    mode = mode_of(agent)
    if mode == "off":
        return []
    if mode == "always":
        return [Slot(time(0, 0), time(23, 59))]
    days = (agent.business_hours or {}).get("days") or []
    if len(days) != 7:
        return []
    out: list[Slot] = []
    for pair in days[when.weekday()] or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        start, end = _parse_time(str(pair[0])), _parse_time(str(pair[1]))
        if start and end and end > start:
            out.append(Slot(start, end))
    return sorted(out, key=lambda slot: slot.start)


def is_open(agent: Agent, now: datetime) -> bool:
    return any(slot.start <= now.time() < slot.end for slot in slots_for(agent, now.date()))


def next_opening(agent: Agent, now: datetime) -> datetime | None:
    """When the doors open next, looking a week ahead at most."""
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        for slot in slots_for(agent, day):
            candidate = datetime.combine(day, slot.start, tzinfo=now.tzinfo)
            if candidate > now:
                return candidate
    return None


def describe(agent: Agent, lang: str = "es") -> str:
    """The weekly schedule, one line per day."""
    text = _text(lang)
    if mode_of(agent) == "always":
        return text["always"]
    lines = []
    for index, name in enumerate(text["days"]):
        # A fixed reference Monday, so weekday() lines up with the index.
        day = date(2024, 1, 1) + timedelta(days=index)
        slots = slots_for(agent, day)
        if slots:
            spans = ", ".join(f"{slot.start:%H:%M}–{slot.end:%H:%M}" for slot in slots)
            lines.append(f"- {name}: {spans}")
        else:
            lines.append(f"- {name}: {text['closed']}")
    return "\n".join(lines)


def prompt_block(agent: Agent, now: datetime, *, has_tool_source: bool = False, lang: str = "es") -> str | None:
    """The hours section for the system prompt, or None when there is nothing
    to say -- no hours written here and no tool that could look them up."""
    text = _text(lang)
    if not is_configured(agent):
        return text["tool_only"] if has_tool_source else None

    if mode_of(agent) == "always":
        return f"{text['always']}\n\n{text['always_state']}"

    open_now = is_open(agent, now)
    state = text["open_now"] if open_now else text["closed_now"]
    if not open_now:
        upcoming = next_opening(agent, now)
        if upcoming:
            when = f"{upcoming:%H:%M}"
            state += (
                text["reopens_today"].format(time=when)
                if upcoming.date() == now.date()
                else text["reopens_day"].format(day=text["days"][upcoming.weekday()].lower(), time=when)
            )

    block = f"{describe(agent, lang)}\n\n{state}\n\n{text['rules']}"
    note = ((agent.business_hours or {}).get("note") or "").strip()
    if note:
        block += "\n\n" + text["note"].format(note=note)
    return block
