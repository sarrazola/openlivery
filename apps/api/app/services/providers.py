"""The AI provider: OpenRouter, bring your own key, one per agency.

OpenRouter fronts every vendor (OpenAI, Anthropic, Google, ...) behind one
OpenAI-compatible API, so an agency configures a single key and picks any
model by its OpenRouter slug (``openai/gpt-5.6-luna``, ``anthropic/claude-sonnet-5``).
The registry keeps its dict shape so a deployment can still swap the base URL
or resolve credentials differently without touching the call sites.
"""

from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, ProviderCredential
from ..security import decrypt_secret

# A deployment may lend credentials to an agency that has not stored its own
# (a shared key, a trial pool). It registers one function at startup; the
# function is asked only when the agency holds no key of its own, so a stored
# key always wins. It returns (base_url, api_key) or None.
CredentialFallback = Callable[[Session, Any, str], "tuple[str, str] | None"]
CredentialProbe = Callable[[Session, Any, str], bool]
_credential_fallback: CredentialFallback | None = None
_credential_available: CredentialProbe | None = None

CredentialSource = Literal["agency", "deployment", "none"]


PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1"},
}
SUPPORTED = tuple(PROVIDERS)
DEFAULT_PROVIDER = "openrouter"


def base_url_for(provider: str) -> str:
    return PROVIDERS[provider]["base_url"]


def register_credential_fallback(fallback: CredentialFallback | None, *, available: CredentialProbe | None = None) -> None:
    """Install what answers when an agency has no key of its own; None removes it.

    ``available`` says whether the fallback would answer right now without
    producing the credentials, for ``credential_source`` and the listing; a
    lender that stops lending (a spent allowance, say) is reported as absent
    instead of handing out a key a request would then be refused on. Without
    it, the fallback itself is asked.
    """
    global _credential_fallback, _credential_available
    _credential_fallback = fallback
    _credential_available = available


def _stored(db: Session, agency_id, provider: str) -> ProviderCredential | None:
    return db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.agency_id == agency_id,
            ProviderCredential.provider == provider,
        )
    )


def credential_source(db: Session, agency_id, provider: str) -> CredentialSource:
    """Where a reply on this provider would get its key from right now."""
    if provider not in PROVIDERS:
        return "none"
    if _stored(db, agency_id, provider) is not None:
        return "agency"
    if _credential_fallback is None:
        return "none"
    if _credential_available is not None:
        return "deployment" if _credential_available(db, agency_id, provider) else "none"
    return "deployment" if _credential_fallback(db, agency_id, provider) is not None else "none"


def resolve_provider_credentials(db: Session, agency_id, provider: str) -> tuple[str, str] | None:
    """(base_url, api_key) for an agency's provider: its stored key, else what the
    deployment's fallback lends, else None."""
    if provider not in PROVIDERS:
        return None
    credential = _stored(db, agency_id, provider)
    if credential is not None:
        return base_url_for(provider), decrypt_secret(credential.encrypted_api_key)
    if _credential_fallback is not None:
        return _credential_fallback(db, agency_id, provider)
    return None


def resolve_agent_credentials(db: Session, agent: Agent) -> tuple[str, str] | None:
    """(base_url, api_key) for the agent's provider using the agency's stored key."""
    return resolve_provider_credentials(db, agent.agency_id, agent.provider)
