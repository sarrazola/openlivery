"""Bounded requests to the official Instagram and Messenger APIs."""

import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException

from ..config import get_settings
from ..security import decrypt_secret

PROVIDERS = {"instagram", "messenger"}
SCOPES = {
    "instagram": {"instagram_business_basic", "instagram_business_manage_messages"},
    "messenger": {"pages_show_list", "pages_messaging", "pages_manage_metadata", "pages_read_engagement", "business_management"},
}
SUBSCRIPTIONS = {
    "instagram": {"messages", "messaging_postbacks", "messaging_seen", "message_reactions", "messaging_referral", "messaging_handover", "standby"},
    "messenger": {"messages", "messaging_postbacks", "message_deliveries", "message_reads", "messaging_referrals", "message_echoes", "messaging_handovers", "standby"},
}


class _RedactTokenURLs(logging.Filter):
    """httpx logs GET URLs, including parameters required by token exchanges."""
    def filter(self, record):
        def redact(value):
            if isinstance(value, (str, httpx.URL)):
                text = str(value)
                if any(key in text for key in ("access_token=", "client_secret=", "input_token=", "fb_exchange_token=", "code=")):
                    return re.sub(r"([?&](?:access_token|client_secret|input_token|fb_exchange_token|code)=)[^&\s\"]+", r"\1[redacted]", text)
            return value
        if isinstance(record.args, tuple):
            record.args = tuple(redact(arg) for arg in record.args)
        record.msg = redact(record.msg)
        return True


logging.getLogger("httpx").addFilter(_RedactTokenURLs())


def provider_name(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unsupported messaging provider")
    return provider


def object_id(value: str) -> str:
    if not re.fullmatch(r"[0-9]{1,64}", str(value)):
        raise HTTPException(400, "The account or recipient ID must contain only digits")
    return str(value)


def path_component(value: str) -> str:
    """Encode an opaque provider ID as one path component, never as a URL."""
    if not isinstance(value, str) or not re.fullmatch(r"[\x21-\x7e]{1,1024}", value):
        raise HTTPException(400, "Invalid provider object identifier")
    return quote(value, safe="").replace(".", "%2E")


def graph_url(provider: str, path: str, *, unversioned: bool = False) -> str:
    provider_name(provider)
    if (not re.fullmatch(r"[A-Za-z0-9_%/+=.-]+", path) or ".." in path or path.startswith("/")
            or "//" in path or re.search(r"%(?![A-Fa-f0-9]{2})", path)):
        raise HTTPException(400, "Invalid API path")
    version = get_settings().social_graph_version
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise HTTPException(503, "The messaging API version is not configured correctly")
    host = "graph.instagram.com" if provider == "instagram" else "graph.facebook.com"
    return f"https://{host}/{'' if unversioned else version + '/'}{path}"


async def _http(method: str, url: str, *, token: str = "", **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(502, "The messaging provider could not be reached") from None
    if len(response.content) > 4 * 1024 * 1024:
        raise HTTPException(502, "The messaging provider returned an oversized response")
    try:
        body = response.json()
    except ValueError:
        raise HTTPException(502, "The messaging provider returned an invalid response") from None
    if not isinstance(body, dict):
        raise HTTPException(502, "The messaging provider returned an invalid response")
    error = body.get("error")
    if response.status_code >= 400 or error:
        code = error.get("code") if isinstance(error, dict) else None
        if code in {102, 190} or response.status_code == 401:
            raise HTTPException(401, "The messaging authorization expired or was revoked. Reconnect this account")
        if code in {10, 200, 294} or response.status_code == 403:
            raise HTTPException(403, "The messaging authorization is missing a required permission or account task")
        if code in {4, 17, 32, 613, 80004} or response.status_code == 429:
            raise HTTPException(429, "The messaging provider rate limit was reached. Retry later")
        if code == 100 or response.status_code == 404:
            raise HTTPException(400 if code == 100 else 404, "The requested provider object or operation is unavailable")
        # Provider error text may reflect tokens or customer content.
        raise HTTPException(502, "The messaging provider rejected the request")
    return body


async def request(provider: str, method: str, path: str, token: str, **kwargs) -> dict:
    return await _http(method, graph_url(provider, path), token=token, **kwargs)


def _proof(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _scopes(value) -> set[str]:
    if isinstance(value, str):
        return set(value.replace(" ", ",").split(",")) - {""}
    if isinstance(value, list):
        return {str(scope) for scope in value if isinstance(scope, str)}
    return set()


def _expiry(seconds) -> str | None:
    try:
        return (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(seconds)))).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


async def verify_account(provider: str, token: str, account_id: str, app_id: str, app_secret: str, *, scopes=None) -> dict:
    """Confirm token/account identity and effective messaging authorization."""
    provider_name(provider)
    account_id, app_id = object_id(account_id), object_id(app_id)
    proof = _proof(token, app_secret)
    fields = "id,user_id,username" if provider == "instagram" else "id,name"
    profile = await request(provider, "GET", "me", token, params={"fields": fields, "appsecret_proof": proof})
    actual_id = str(profile.get("user_id") or profile.get("id") or "")
    if actual_id != account_id:
        raise HTTPException(400, "This access token belongs to a different account")
    granted = _scopes(scopes)
    expires_at = None
    if provider == "messenger":
        debug = await request(provider, "GET", "debug_token", f"{app_id}|{app_secret}", params={"input_token": token})
        details = debug.get("data") or {}
        if not details.get("is_valid") or str(details.get("app_id")) != app_id or details.get("type") != "PAGE":
            raise HTTPException(400, "Use a valid Page access token issued by this application")
        granted = _scopes(details.get("scopes"))
        if not {"pages_messaging", "pages_manage_metadata"}.issubset(granted):
            raise HTTPException(403, "The Page token requires messaging and webhook management permissions")
        expirations = [int(details.get(key) or 0) for key in ("expires_at", "data_access_expires_at")]
        if any(expirations):
            expires_at = datetime.fromtimestamp(min(value for value in expirations if value > 0), timezone.utc).isoformat()
    elif granted and not SCOPES[provider].issubset(granted):
        raise HTTPException(403, "Instagram messaging permission was not granted")
    # This read requires messaging permission even when no conversation exists.
    await request(provider, "GET", f"{account_id}/conversations", token, params={"limit": 1, "appsecret_proof": proof})
    return {"id": actual_id, "name": profile.get("name") or profile.get("username") or actual_id,
            "username": profile.get("username"), "scopes": sorted(granted), "expires_at": expires_at}


async def subscribe(provider: str, token: str, account_id: str, app_id: str, app_secret: str) -> bool:
    """Subscribe and read back this app's fields. Return whether it was new."""
    account_id, app_id = object_id(account_id), object_id(app_id)
    proof = _proof(token, app_secret)
    path = f"{account_id}/subscribed_apps"
    before = await request(provider, "GET", path, token, params={"appsecret_proof": proof})
    existing = next((row for row in before.get("data", []) if str(row.get("id")) == app_id), None)
    fields = SUBSCRIPTIONS[provider] | set((existing or {}).get("subscribed_fields") or [])
    await request(provider, "POST", path, token, data={"subscribed_fields": ",".join(sorted(fields)), "appsecret_proof": proof})
    try:
        after = await request(provider, "GET", path, token, params={"appsecret_proof": proof})
        ours = next((row for row in after.get("data", []) if str(row.get("id")) == app_id), None)
        if not ours or not SUBSCRIPTIONS[provider].issubset(set(ours.get("subscribed_fields") or [])):
            raise HTTPException(502, "The required messaging webhook subscription could not be confirmed")
    except HTTPException:
        if existing is None:
            try:
                await unsubscribe(provider, token, account_id, app_secret)
            except HTTPException:
                pass
        raise
    return existing is None


async def unsubscribe(provider: str, token: str, account_id: str, app_secret: str) -> None:
    await request(provider, "DELETE", f"{object_id(account_id)}/subscribed_apps", token, params={"appsecret_proof": _proof(token, app_secret)})


async def exchange_code(provider: str, code: str, config) -> list[dict]:
    """Return private account choices; callers must encrypt this result."""
    if provider == "instagram":
        short = await _http("POST", "https://api.instagram.com/oauth/access_token", data={
            "client_id": config.app_id, "client_secret": config.app_secret, "grant_type": "authorization_code",
            "redirect_uri": config.redirect_uri, "code": code,
        })
        if isinstance(short.get("data"), list) and short["data"]:
            short = short["data"][0]
        scopes = _scopes(short.get("permissions"))
        if not SCOPES[provider].issubset(scopes) or not short.get("access_token"):
            raise HTTPException(403, "Instagram messaging permission was not granted")
        long = await _http("GET", graph_url(provider, "access_token", unversioned=True), params={
            "grant_type": "ig_exchange_token", "client_secret": config.app_secret, "access_token": short["access_token"],
        })
        token = long.get("access_token")
        if not token or not _expiry(long.get("expires_in")):
            raise HTTPException(502, "The provider did not return a renewable Instagram token")
        profile = await request(provider, "GET", "me", token, params={"fields": "id,user_id,username", "appsecret_proof": _proof(token, config.app_secret)})
        account_id = object_id(str(profile.get("user_id") or profile.get("id") or ""))
        return [{"id": account_id, "name": profile.get("username") or account_id, "username": profile.get("username"),
                 "access_token": token, "scopes": sorted(scopes), "expires_at": _expiry(long["expires_in"])}]
    short = await _http("GET", graph_url(provider, "oauth/access_token"), params={
        "client_id": config.app_id, "client_secret": config.app_secret, "redirect_uri": config.redirect_uri, "code": code,
    })
    if not short.get("access_token"):
        raise HTTPException(502, "The provider did not return an authorization token")
    long = await _http("GET", graph_url(provider, "oauth/access_token"), params={
        "grant_type": "fb_exchange_token", "client_id": config.app_id, "client_secret": config.app_secret,
        "fb_exchange_token": short["access_token"],
    })
    token = long.get("access_token")
    if not token:
        raise HTTPException(502, "The provider did not return an authorization token")
    permissions = await request(provider, "GET", "me/permissions", token, params={"appsecret_proof": _proof(token, config.app_secret)})
    granted = {row.get("permission") for row in permissions.get("data", []) if row.get("status") == "granted"}
    if not SCOPES[provider].issubset(granted):
        raise HTTPException(403, "Required Page permissions were not granted")
    accounts, after = [], None
    for _ in range(50):
        params = {"fields": "id,name,access_token,tasks", "limit": 100, "appsecret_proof": _proof(token, config.app_secret)}
        if after:
            params["after"] = after
        page = await request(provider, "GET", "me/accounts", token, params=params)
        for row in page.get("data", []):
            if row.get("access_token") and {"MESSAGING", "MODERATE"}.issubset(set(row.get("tasks") or [])):
                accounts.append({"id": object_id(str(row["id"])), "name": row.get("name") or row["id"],
                                 "access_token": row["access_token"], "scopes": sorted(granted), "expires_at": None})
        paging = page.get("paging") or {}
        # Never follow provider-supplied URLs with an authorization header.
        after = (paging.get("cursors") or {}).get("after") if paging.get("next") else None
        if not after:
            break
    if not accounts:
        raise HTTPException(400, "No authorized Pages with messaging and moderation tasks were found")
    return accounts


async def refresh_instagram(token: str) -> dict:
    data = await _http("GET", graph_url("instagram", "refresh_access_token", unversioned=True), params={"grant_type": "ig_refresh_token", "access_token": token})
    expires = _expiry(data.get("expires_in"))
    if not data.get("access_token") or not expires:
        raise HTTPException(502, "The provider returned an invalid token refresh response")
    return {"access_token": data["access_token"], "expires_at": expires}


def _delivery(channel, recipient_id: str, human_agent: bool) -> tuple[str, dict]:
    if channel.status != "connected" or not channel.is_enabled or not channel.encrypted_access_token:
        raise HTTPException(409, "Connect this messaging channel before replying")
    if human_agent:
        approved = channel.human_agent_enabled
        if getattr(channel, "connection_source", "") == "managed":
            from .social_connections import get_app_config
            approved = approved and get_app_config(channel.provider).human_agent_enabled
        if not approved:
            raise HTTPException(409, "Human Agent support has not been enabled for this connection")
    payload = {"recipient": {"id": object_id(recipient_id)}}
    if human_agent:
        payload.update({"messaging_type": "MESSAGE_TAG", "tag": "HUMAN_AGENT"})
    elif channel.provider == "messenger":
        payload["messaging_type"] = "RESPONSE"
    token = decrypt_secret(channel.encrypted_access_token)
    if getattr(channel, "encrypted_app_secret", None):
        payload["appsecret_proof"] = _proof(token, decrypt_secret(channel.encrypted_app_secret))
    return token, payload


def _message_id(data: dict) -> str:
    value = data.get("message_id")
    if not isinstance(value, str) or not re.fullmatch(r"[\x21-\x7e]{1,1024}", value):
        raise HTTPException(502, "The messaging provider did not confirm delivery")
    return value


async def send_text(channel, recipient_id: str, text: str, *, human_agent: bool = False) -> str:
    if not text or (channel.provider == "instagram" and len(text.encode("utf-8")) > 1000) or (channel.provider == "messenger" and len(text) > 2000):
        raise HTTPException(400, "The message exceeds this channel's text limit")
    token, payload = _delivery(channel, recipient_id, human_agent)
    payload["message"] = {"text": text}
    data = await request(channel.provider, "POST", f"{object_id(channel.external_account_id)}/messages", token, json=payload)
    return _message_id(data)


async def send_media(channel, recipient_id: str, kind: str, url: str, *, human_agent: bool = False) -> str:
    kind = "file" if kind == "document" else kind
    parsed = urlsplit(url)
    if kind not in {"image", "audio", "video", "file"} or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Use a supported attachment with a public HTTPS download URL")
    token, payload = _delivery(channel, recipient_id, human_agent)
    payload["message"] = {"attachment": {"type": kind, "payload": {"url": url}}}
    data = await request(channel.provider, "POST", f"{object_id(channel.external_account_id)}/messages", token, json=payload)
    return _message_id(data)


async def mark_read(channel, recipient_id: str) -> None:
    token, payload = _delivery(channel, recipient_id, False)
    payload.pop("messaging_type", None)
    payload["sender_action"] = "mark_seen"
    await request(channel.provider, "POST", f"{object_id(channel.external_account_id)}/messages", token, json=payload)
