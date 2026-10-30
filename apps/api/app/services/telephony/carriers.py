"""The phone carriers whose numbers ring the agent: Twilio and Telnyx.

OpenLivery only reads the agency's numbers and, for Telnyx, points one at
ElevenLabs over SIP. Buying numbers stays in each carrier's console.
"""

import httpx

from . import TelephonyError

TIMEOUT = 20
TWILIO_API = "https://api.twilio.com/2010-04-01"
TELNYX_API = "https://api.telnyx.com/v2"
# Where ElevenLabs receives SIP calls; the number goes before the "@".
ELEVENLABS_SIP_HOST = "sip.rtc.elevenlabs.io"
ELEVENLABS_SIP_PORT = 5060
TELNYX_SIP_HOST = "sip.telnyx.com"
CARRIERS = ("twilio", "telnyx")


async def _twilio(secret: dict, method: str, path: str, **kwargs) -> dict:
    sid, token = secret.get("account_sid", ""), secret.get("auth_token", "")
    async with httpx.AsyncClient(timeout=TIMEOUT, auth=(sid, token)) as client:
        try:
            response = await client.request(method, f"{TWILIO_API}/Accounts/{sid}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise TelephonyError(f"Twilio could not be reached: {exc.__class__.__name__}") from exc
    if response.status_code == 401:
        raise TelephonyError("Twilio rejected the Account SID or the Auth Token.")
    if response.status_code >= 400:
        message = response.json().get("message") if response.content else ""
        raise TelephonyError(f"Twilio refused the request ({response.status_code}): {message or response.text[:200]}")
    return response.json() if response.content else {}


async def _telnyx(secret: dict, method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {secret.get('api_key', '')}"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        try:
            response = await client.request(method, f"{TELNYX_API}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise TelephonyError(f"Telnyx could not be reached: {exc.__class__.__name__}") from exc
    if response.status_code == 401:
        raise TelephonyError("Telnyx rejected the API key.")
    if response.status_code >= 400:
        errors = response.json().get("errors") if response.content else None
        detail = (errors[0].get("detail") or errors[0].get("title")) if errors else response.text[:200]
        raise TelephonyError(f"Telnyx refused the request ({response.status_code}): {detail}")
    return response.json() if response.content else {}


async def validate(provider: str, secret: dict) -> str:
    if provider == "twilio":
        account = await _twilio(secret, "GET", ".json")
        return f"Twilio connected: {account.get('friendly_name') or secret.get('account_sid')}."
    if provider == "telnyx":
        await _telnyx(secret, "GET", "/phone_numbers", params={"page[size]": 1})
        return "Telnyx connected."
    raise TelephonyError(f"Unknown phone provider: {provider}")


async def list_numbers(provider: str, secret: dict) -> list[dict]:
    """The account's numbers that can take voice calls: [{id, phone_number, name}]."""
    if provider == "twilio":
        found = await _twilio(secret, "GET", "/IncomingPhoneNumbers.json", params={"PageSize": 100})
        return [
            {"id": n["sid"], "phone_number": n["phone_number"], "name": n.get("friendly_name") or ""}
            for n in found.get("incoming_phone_numbers", [])
            if (n.get("capabilities") or {}).get("voice", True)
        ]
    if provider == "telnyx":
        found = await _telnyx(secret, "GET", "/phone_numbers", params={"page[size]": 100})
        return [
            {"id": n["id"], "phone_number": n["phone_number"], "name": n.get("connection_name") or ""}
            for n in found.get("data", [])
        ]
    raise TelephonyError(f"Unknown phone provider: {provider}")


async def telnyx_route_to_elevenlabs(secret: dict, number_id: str, connection_name: str) -> dict:
    """Send a Telnyx number's calls to ElevenLabs: an FQDN connection whose
    target is ElevenLabs' SIP host, with the number assigned to it. Returns
    the SIP configs ElevenLabs needs to import the number."""
    connection = (await _telnyx(secret, "POST", "/fqdn_connections", json={
        "connection_name": connection_name,
        "transport_protocol": "TCP",
        "inbound": {"ani_number_format": "+E.164", "dnis_number_format": "+e164"},
    }))["data"]
    await _telnyx(secret, "POST", "/fqdns", json={
        "connection_id": connection["id"], "fqdn": ELEVENLABS_SIP_HOST, "port": ELEVENLABS_SIP_PORT, "dns_record_type": "a",
    })
    await _telnyx(secret, "PATCH", f"/phone_numbers/{number_id}", json={"connection_id": connection["id"]})
    return {
        "connection_id": connection["id"],
        "inbound": {"media_encryption": "allowed"},
        "outbound": {"address": TELNYX_SIP_HOST, "transport": "tcp", "media_encryption": "allowed"},
    }


async def telnyx_release(secret: dict, connection_id: str) -> None:
    await _telnyx(secret, "DELETE", f"/fqdn_connections/{connection_id}")
