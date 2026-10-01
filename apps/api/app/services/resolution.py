"""Agent-initiated resolution: the model decides WHEN a case is settled.

An agent with ``resolve_enabled`` gets a tool to say the contact's request is
done. Like escalation, the handler runs inside the generation loop, so it only
records the request; the caller hands it to ``follow_ups.after_agent_reply``,
which resolves the conversation a short while later unless the contact writes
first. The farewell the model writes goes out while the case is still open.

Escalation wins over it: a case that needs a person is not settled.
"""

from dataclasses import dataclass

from ..models import Agent
from .tools.specs import ToolSpec

# LLM-facing text, in the language of the agent's prompt like the rest of it.
_RULES = {
    "es": (
        "CIERRE DE LA CONVERSACIÓN: dispones de la herramienta resolve_conversation. Úsala solo cuando lo que el "
        "cliente necesitaba quedó atendido y no queda nada pendiente: confirmó que no necesita nada más, agradeció "
        "y se despidió, o se completó la gestión que buscaba.\n"
        "No la uses si le hiciste una pregunta que sigue sin respuesta, si todavía espera algo de ti o del negocio, "
        "o si tienes dudas: en ese caso deja la conversación abierta.\n"
        "Al usarla, despídete con naturalidad en tu respuesta, sin decir que cierras el caso ni mencionar la "
        "herramienta."
    ),
    "en": (
        "CLOSING THE CONVERSATION: you have the resolve_conversation tool. Use it only when what the customer "
        "needed has been taken care of and nothing is pending: they confirmed they need nothing else, thanked you "
        "and said goodbye, or the request they came for was completed.\n"
        "Do not use it if you asked a question that is still unanswered, if they are still waiting for something "
        "from you or the business, or if you are in doubt: leave the conversation open then.\n"
        "When you use it, say goodbye naturally in your reply, without saying that you are closing the case or "
        "mentioning the tool."
    ),
}


@dataclass
class ResolutionRequest:
    reason: str = ""


def resolution_prompt(agent: Agent) -> str:
    return _RULES[agent.prompt_language if agent.prompt_language in _RULES else "es"]


def build_resolution_spec(holder: list[ResolutionRequest]) -> ToolSpec:
    def handler(args: dict) -> tuple[str, bool]:
        reason = str(args.get("reason") or "").strip()[:300]
        if not reason:
            return "Provide a short reason: what was settled for the customer.", True
        holder.clear()
        holder.append(ResolutionRequest(reason=reason))
        return (
            "Resolution registered. Say goodbye naturally in your own words; do not mention closing the case.",
            False,
        )

    return ToolSpec(
        name="resolve_conversation",
        description=(
            "Mark this conversation as resolved because the customer's request is settled and nothing is pending."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "One short sentence on what was settled, in the customer's language"},
            },
            "required": ["reason"],
        },
        handler=handler,
    )
