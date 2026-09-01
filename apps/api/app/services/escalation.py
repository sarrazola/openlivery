"""AI-initiated escalation: the model decides WHEN, the data decides WHERE.

The model sees the built-in triggers and the business rules (conditions only,
numbered - destinations never reach the prompt) and calls the escalate tool.
The tool handler runs inside the generation loop, so it only validates and
records the request; ``apply_escalation`` performs the real hand-over
afterwards, with the conversation in hand: human mode, tray, routing, the
activity line and the notifications.

Destination precedence: the matched rule's destination, else the agent's
default escalation destination, else the tray that attends the conversation's
channel, else the client's default tray, else nobody - the conversation waits
in human mode unassigned and every portal device rings.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, Conversation, EscalationRule, PortalUser, Team, now_utc
from .conversation_state import assign, record_activity, set_team
from .notifications import notify_assigned, notify_needs_human
from .routing import route_conversation
from .tools.specs import ToolSpec

TRIGGERS = ("frustration", "human_request", "cannot_solve")

# Spanish like the rest of the LLM-facing scaffolding.
ESCALATION_RULES_INTRO = (
    "ESCALAMIENTO A PERSONAS: dispones de la herramienta escalate_to_human. Úsala cuando toque, no antes:\n"
    "- trigger=frustration: el cliente muestra molestia repetida, groserías o una mala experiencia con el negocio.\n"
    "- trigger=human_request: pide explícitamente hablar con una persona.\n"
    "- trigger=cannot_solve: tras intentarlo, no puedes resolver lo que necesita.\n"
)
ESCALATION_BUSINESS_INTRO = (
    "Además, decisiones del negocio (si el último mensaje coincide con una en contexto, escala con rule=N):\n"
)
ESCALATION_CLOSING = (
    "Al escalar, la herramienta registra el traslado; tu respuesta debe despedirte con calidez y naturalidad "
    "diciendo que una persona o un equipo especializado continúa la conversación. Redáctala tú, variada, sin "
    "mencionar nombres internos de equipos ni la palabra 'regla'. Nunca inventes que escalaste sin usar la "
    "herramienta, y nunca la uses para preguntas que sí puedes resolver."
)


def active_rules(db: Session, agent: Agent) -> list[EscalationRule]:
    return list(
        db.scalars(
            select(EscalationRule)
            .where(
                EscalationRule.agent_id == agent.id,
                EscalationRule.is_active.is_(True),
            )
            .order_by(EscalationRule.position)
        )
    )


def escalation_enabled(db: Session, agent: Agent, rules: list[EscalationRule]) -> bool:
    """Escalation only enters the prompt when it can land somewhere: a rule
    with a destination, the agent's default, or any team of the client."""
    if any(rule.team_id or rule.assignee_id for rule in rules):
        return True
    if agent.escalation_team_id or agent.escalation_assignee_id:
        return True
    return db.scalar(select(Team.id).where(Team.client_id == agent.client_id).limit(1)) is not None


def escalation_prompt(rules: list[EscalationRule]) -> str:
    parts = [ESCALATION_RULES_INTRO]
    numbered = [rule for rule in rules if rule.team_id or rule.assignee_id]
    if numbered:
        parts.append(ESCALATION_BUSINESS_INTRO)
        parts.extend(f"[{index}] {rule.condition.strip()}\n" for index, rule in enumerate(numbered, start=1))
    parts.append(ESCALATION_CLOSING)
    return "".join(parts)


@dataclass
class EscalationRequest:
    reason: str = ""
    trigger: str | None = None
    rule: EscalationRule | None = None


def build_escalation_spec(rules: list[EscalationRule], holder: list[EscalationRequest]) -> ToolSpec:
    numbered = [rule for rule in rules if rule.team_id or rule.assignee_id]

    def handler(args: dict) -> tuple[str, bool]:
        rule_number = args.get("rule")
        trigger = args.get("trigger")
        reason = str(args.get("reason") or "").strip()[:300]
        matched: EscalationRule | None = None
        if rule_number is not None:
            try:
                matched = numbered[int(rule_number) - 1]
            except (ValueError, TypeError, IndexError):
                return ("Unknown rule number; use one of the numbered business rules or a trigger.", True)
        elif trigger not in TRIGGERS:
            return ("Provide either rule (a business rule number) or a valid trigger.", True)
        holder.clear()
        holder.append(EscalationRequest(reason=reason, trigger=trigger if matched is None else None, rule=matched))
        return (
            "Escalation registered; a person will continue this conversation. Now close warmly in your own "
            "words, without internal team names.",
            False,
        )

    return ToolSpec(
        name="escalate_to_human",
        description=(
            "Hand this conversation to a person or a specialised team. Use it when a business rule matches "
            "(rule=N), or with a trigger: frustration, human_request, cannot_solve."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "rule": {"type": "integer", "description": "Number of the matched business rule"},
                "trigger": {"type": "string", "enum": list(TRIGGERS)},
                "reason": {"type": "string", "description": "One short sentence on why, in the customer's language"},
            },
        },
        handler=handler,
    )


def _channel_team(db: Session, agent: Agent, channel_key: str | None) -> Team | None:
    if not channel_key:
        return None
    for team in db.scalars(select(Team).where(Team.client_id == agent.client_id)):
        if channel_key in (team.channels or []):
            return team
    return None


def resolve_destination(
    db: Session, agent: Agent, conversation: Conversation, request: EscalationRequest
) -> tuple[Team | None, PortalUser | None]:
    if request.rule is not None:
        if request.rule.assignee_id:
            person = db.get(PortalUser, request.rule.assignee_id)
            if person and person.is_active:
                return None, person
        if request.rule.team_id:
            team = db.get(Team, request.rule.team_id)
            if team:
                return team, None
    if request.trigger is not None or request.rule is not None:
        if agent.escalation_assignee_id:
            person = db.get(PortalUser, agent.escalation_assignee_id)
            if person and person.is_active:
                return None, person
        if agent.escalation_team_id:
            team = db.get(Team, agent.escalation_team_id)
            if team:
                return team, None
        team = _channel_team(db, agent, conversation.channel)
        if team:
            return team, None
        team = db.scalar(select(Team).where(Team.client_id == agent.client_id, Team.is_default.is_(True)))
        if team:
            return team, None
    return None, None


async def apply_escalation(
    db: Session, conversation: Conversation, agent: Agent, request: EscalationRequest
) -> None:
    """The hand-over itself, after the reply was generated. Never raises for
    routing reasons: an escalation with nowhere to land still reaches people
    as an unassigned human conversation."""
    if conversation.status == "resolved":
        return
    team, person = resolve_destination(db, agent, conversation, request)
    if conversation.mode != "human":
        conversation.mode = "human"
        conversation.taken_over_at = now_utc()
    target = person.name if person else (team.name if team else "a person")
    reason = request.reason or (request.rule.condition[:120] if request.rule else request.trigger or "")
    record_activity(db, conversation, "escalated", actor=agent.name, details={"target": target, "reason": reason})
    if team:
        set_team(db, conversation, team, actor=agent.name)
    routed = None
    if person:
        assign(db, conversation, person, actor=agent.name)
        routed = person
    elif team:
        routed = route_conversation(db, conversation, actor=agent.name)
    db.commit()
    if routed:
        await notify_assigned(db, conversation, routed, agent.name)
    else:
        await notify_needs_human(db, conversation, f"{agent.name}: {reason}" if reason else agent.name, team=team)
