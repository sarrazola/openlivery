"""The ElevenLabs Agents API, with the agency's own key.

OpenLivery keeps one ElevenLabs agent per phone line, carrying the
OpenLivery agent's prompt: ElevenLabs runs the whole call (speech
recognition, turn taking, the model, the voice). Numbers are imported into
the workspace and assigned to that agent.
"""

import re

import httpx

from . import TelephonyError

API = "https://api.elevenlabs.io/v1"
TIMEOUT = 20
# Events the post-call webhook reports: the transcript and calls that never connected.
WEBHOOK_EVENTS = ["transcript", "call_initiation_failure"]


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    detail = body.get("detail") if isinstance(body, dict) else body
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)[:300]
    if isinstance(detail, list) and detail:
        first = detail[0]
        return str(first.get("msg") if isinstance(first, dict) else first)[:300]
    return str(detail)[:300]


async def _request(api_key: str, method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=API, timeout=TIMEOUT, headers={"xi-api-key": api_key}) as client:
        try:
            response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise TelephonyError(f"ElevenLabs could not be reached: {exc.__class__.__name__}") from exc
    if response.status_code == 401:
        raise TelephonyError(_unauthorized(response))
    if response.status_code >= 400:
        raise TelephonyError(f"ElevenLabs refused the request ({response.status_code}): {_detail(response)}")
    return response.json() if response.content else {}


def _unauthorized(response: httpx.Response) -> str:
    """A restricted key answers 401 naming the permission it lacks; say which,
    since the fix is on the key and not in OpenLivery."""
    message = _detail(response)
    missing = re.search(r"missing the permission (\w+)", message)
    if missing:
        return f"The ElevenLabs API key is missing the {missing.group(1)} permission. Allow it on the key in ElevenLabs and try again."
    return "ElevenLabs rejected the API key."


async def validate_key(api_key: str) -> str:
    """Prove the key works for Agents, the part of the API calls need, and may
    create the post-call webhook. The webhook check posts an empty body: a key
    without the permission gets a 401, one with it a 422 about the body, and
    nothing is created either way."""
    await _request(api_key, "GET", "/convai/agents", params={"page_size": 1})
    async with httpx.AsyncClient(base_url=API, timeout=TIMEOUT, headers={"xi-api-key": api_key}) as client:
        try:
            response = await client.post("/workspace/webhooks", json={})
        except httpx.HTTPError as exc:
            raise TelephonyError(f"ElevenLabs could not be reached: {exc.__class__.__name__}") from exc
    if response.status_code == 401:
        raise TelephonyError(_unauthorized(response))
    return "ElevenLabs connected."


async def list_voices(api_key: str, *, language: str = "es", search: str = "") -> list[dict]:
    """Conversational voices from the shared library in the agents' language,
    the most used first: a phone agent needs a native accent, and the library
    has local ones (Colombian, Mexican...) that the default voices lack."""
    params = {"language": language, "use_cases": "conversational", "page_size": 30, "sort": "usage_character_count_1y"}
    if search:
        params["search"] = search
    found = await _request(api_key, "GET", "/shared-voices", params=params)
    voices = [_voice(voice) for voice in found.get("voices", [])]
    return [voice for voice in voices if voice["voice_id"]]


def _voice(voice: dict) -> dict:
    return {
        "voice_id": voice.get("voice_id"),
        "name": voice.get("name") or "",
        "accent": voice.get("accent") or (voice.get("labels") or {}).get("accent") or "",
        "gender": voice.get("gender") or (voice.get("labels") or {}).get("gender") or "",
        "description": (voice.get("description") or "")[:240],
        "preview_url": voice.get("preview_url"),
    }


async def find_voice(api_key: str, voice_id: str) -> dict | None:
    """A voice by its id, from the workspace or the shared library, for an
    operator who pasted one they found there; None when neither has it."""
    async with httpx.AsyncClient(base_url=API, timeout=TIMEOUT, headers={"xi-api-key": api_key}) as client:
        own = await client.get(f"/voices/{voice_id}")
    if own.status_code == 200:
        return _voice(own.json())
    shared = await _request(api_key, "GET", "/shared-voices", params={"search": voice_id, "page_size": 10})
    voice = next((v for v in shared.get("voices", []) if v.get("voice_id") == voice_id), None)
    return _voice(voice) if voice else None


async def ensure_voice(api_key: str, voice_id: str) -> str:
    """An agent speaks only with a voice in the workspace: add a library voice
    the first time. Returns the voice's name."""
    async with httpx.AsyncClient(base_url=API, timeout=TIMEOUT, headers={"xi-api-key": api_key}) as client:
        own = await client.get(f"/voices/{voice_id}")
    if own.status_code == 200:
        return own.json().get("name") or ""
    shared = await _request(api_key, "GET", "/shared-voices", params={"search": voice_id, "page_size": 10})
    voice = next((v for v in shared.get("voices", []) if v.get("voice_id") == voice_id), None)
    if not voice:
        raise TelephonyError("That voice is no longer in the ElevenLabs library. Choose another one.")
    await _request(
        api_key, "POST", f"/voices/add/{voice['public_owner_id']}/{voice_id}", json={"new_name": voice.get("name") or voice_id}
    )
    return voice.get("name") or ""


async def create_webhook(api_key: str, name: str, url: str) -> tuple[str, str | None]:
    """A workspace webhook signed with HMAC. Returns (webhook id, signing secret)."""
    created = await _request(
        api_key, "POST", "/workspace/webhooks", json={"settings": {"auth_type": "hmac", "name": name, "webhook_url": url}}
    )
    return created["webhook_id"], created.get("webhook_secret")


async def delete_webhook(api_key: str, webhook_id: str) -> None:
    await _request(api_key, "DELETE", f"/workspace/webhooks/{webhook_id}")


async def upsert_agent(api_key: str, agent_id: str | None, body: dict) -> str:
    if agent_id:
        await _request(api_key, "PATCH", f"/convai/agents/{agent_id}", json=body)
        return agent_id
    return (await _request(api_key, "POST", "/convai/agents/create", json=body))["agent_id"]


async def delete_agent(api_key: str, agent_id: str) -> None:
    await _request(api_key, "DELETE", f"/convai/agents/{agent_id}")


async def import_twilio_number(api_key: str, *, phone_number: str, label: str, sid: str, token: str, agent_id: str) -> str:
    """ElevenLabs points the Twilio number's calls at itself."""
    body = {"provider": "twilio", "phone_number": phone_number, "label": label, "sid": sid, "token": token, "agent_id": agent_id}
    return (await _request(api_key, "POST", "/convai/phone-numbers", json=body))["phone_number_id"]


async def import_sip_number(api_key: str, *, phone_number: str, label: str, inbound: dict, outbound: dict, agent_id: str) -> str:
    body = {
        "provider": "sip_trunk", "phone_number": phone_number, "label": label, "agent_id": agent_id,
        "inbound_trunk_config": inbound, "outbound_trunk_config": outbound,
    }
    return (await _request(api_key, "POST", "/convai/phone-numbers", json=body))["phone_number_id"]


async def assign_number(api_key: str, phone_number_id: str, agent_id: str) -> None:
    await _request(api_key, "PATCH", f"/convai/phone-numbers/{phone_number_id}", json={"agent_id": agent_id})


async def release_number(api_key: str, phone_number_id: str) -> None:
    await _request(api_key, "DELETE", f"/convai/phone-numbers/{phone_number_id}")
