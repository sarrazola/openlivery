"""Bounded calls to the Telegram Bot API.

Every request carries the bot token in its path, so nothing here ever logs or
raises a URL: failures are reported by their kind and Telegram's description.
"""

import asyncio
import html
import logging
import re
import time

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
# What @BotFather issues: the bot's numeric id, a colon and the secret part.
TOKEN_PATTERN = re.compile(r"^[0-9]{3,20}:[A-Za-z0-9_-]{20,100}$")
# Telegram serves a bot at most this much through getFile.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
# A sendPhoto upload larger than this is refused; it travels as a document.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
TEXT_LIMIT = 4096
# Only private messages are asked for: groups and channels are not a support
# conversation with one person.
ALLOWED_UPDATES = ["message"]
PHOTO_MIMES = {"image/jpeg", "image/png", "image/webp"}
VOICE_MIMES = {"audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/m4a"}

_TOKEN_IN_PATH = re.compile(r"/(file/)?bot[0-9]+:[A-Za-z0-9_-]+")


class _RedactBotTokens(logging.Filter):
    """httpx logs every request URL, and a Bot API URL holds the token."""

    def filter(self, record):
        def redact(value):
            if isinstance(value, (str, httpx.URL)) and "/bot" in str(value):
                return _TOKEN_IN_PATH.sub(lambda match: f"/{match.group(1) or ''}bot[redacted]", str(value))
            return value
        if isinstance(record.args, tuple):
            record.args = tuple(redact(arg) for arg in record.args)
        record.msg = redact(record.msg)
        return True


logging.getLogger("httpx").addFilter(_RedactBotTokens())


def valid_token(token: str) -> bool:
    return bool(TOKEN_PATTERN.fullmatch(token or ""))


def _refusal(code: int, description: str) -> HTTPException:
    text = " ".join(description.split())[:300] or "Telegram refused the request"
    if code == 429:
        return HTTPException(429, text)
    if code in (401, 404):
        # 404 is what Telegram answers for a token that names no bot.
        return HTTPException(401, "Telegram rejected the bot token. Issue a new one with @BotFather and connect the bot again.")
    if code == 403:
        # The person blocked the bot or deleted the chat. The bot itself is
        # fine, so this must not read as a revoked authorization.
        return HTTPException(409, "The contact blocked the bot or deleted the chat, so Telegram did not deliver the message.")
    if code >= 500:
        return HTTPException(502, f"Telegram is unavailable: {text}")
    return HTTPException(422, f"Telegram refused the request: {text}")


async def call(token: str, method: str, *, data: dict | None = None, files: dict | None = None,
               timeout: float = 20) -> object:
    """POST one Bot API method and return its ``result``."""
    if not valid_token(token):
        raise HTTPException(401, "Telegram rejected the bot token. Issue a new one with @BotFather and connect the bot again.")
    url = f"{API_BASE}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if files:
                response = await client.post(url, data={key: str(value) for key, value in (data or {}).items()}, files=files)
            else:
                response = await client.post(url, json=data or {})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Telegram could not be reached ({type(exc).__name__}).") from None
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, f"Telegram answered with HTTP {response.status_code}.") from None
    if isinstance(payload, dict) and payload.get("ok"):
        return payload.get("result")
    payload = payload if isinstance(payload, dict) else {}
    raise _refusal(int(payload.get("error_code") or response.status_code or 502), str(payload.get("description") or ""))


async def get_me(token: str) -> dict:
    me = await call(token, "getMe")
    if not isinstance(me, dict) or not me.get("is_bot") or not me.get("id"):
        raise HTTPException(422, "This token does not belong to a Telegram bot.")
    return me


async def set_webhook(token: str, url: str, secret: str) -> None:
    await call(token, "setWebhook", data={
        "url": url, "secret_token": secret, "allowed_updates": ALLOWED_UPDATES, "max_connections": 10,
    })


async def delete_webhook(token: str) -> None:
    await call(token, "deleteWebhook", data={"drop_pending_updates": False})


def _message_id(chat_id: str, result: object) -> str:
    if not isinstance(result, dict) or not result.get("message_id"):
        raise HTTPException(502, "Telegram returned no message id.")
    return external_id(chat_id, result["message_id"])


def external_id(chat_id, message_id) -> str:
    """Telegram numbers messages per chat; the chat makes the id unique per bot."""
    return f"{chat_id}:{message_id}"


async def send_text(token: str, chat_id: str, text: str) -> str:
    formatted = markdown_to_telegram_html(text)
    try:
        result = await call(token, "sendMessage", data={"chat_id": chat_id, "text": formatted, "parse_mode": "HTML"})
    except HTTPException as exc:
        # Markup Telegram cannot parse is not worth losing the reply over.
        if exc.status_code != 422 or "parse" not in str(exc.detail).lower():
            raise
        result = await call(token, "sendMessage", data={"chat_id": chat_id, "text": strip_markdown(text)})
    return _message_id(chat_id, result)


async def send_typing(token: str, chat_id: str) -> None:
    await call(token, "sendChatAction", data={"chat_id": chat_id, "action": "typing"}, timeout=5)


# Telegram shows a chat action for about five seconds, and a reply takes longer
# to write. While one is being written the action is sent again, until the
# reply leaves (``stop_typing``) or a minute passes, whichever comes first.
TYPING_REPEAT_SECONDS = 4.5
TYPING_LIMIT_SECONDS = 60
_typing: dict[str, asyncio.Task] = {}


def _typing_key(token: str, chat_id: str) -> str:
    return f"{token.split(':', 1)[0]}:{chat_id}"


async def keep_typing(token: str, chat_id: str) -> None:
    """Show the bot typing now and keep showing it until ``stop_typing``."""
    stop_typing(token, chat_id)
    await send_typing(token, chat_id)

    async def repeat() -> None:
        deadline = time.monotonic() + TYPING_LIMIT_SECONDS
        while time.monotonic() + TYPING_REPEAT_SECONDS < deadline:
            await asyncio.sleep(TYPING_REPEAT_SECONDS)
            try:
                await send_typing(token, chat_id)
            except HTTPException:
                return

    key = _typing_key(token, chat_id)
    task = asyncio.create_task(repeat())
    _typing[key] = task
    task.add_done_callback(lambda done: _typing.pop(key, None) if _typing.get(key) is done else None)


def stop_typing(token: str, chat_id: str) -> None:
    task = _typing.pop(_typing_key(token, chat_id), None)
    if task:
        task.cancel()


async def send_file(token: str, chat_id: str, kind: str, data: bytes, mime: str, filename: str | None) -> str:
    """Upload ``data`` with the method that shows it the way it was meant:
    a photo, a voice note, a video or a document."""
    mime = (mime or "application/octet-stream").split(";")[0].strip().lower()
    if kind == "image" and mime in PHOTO_MIMES and len(data) <= MAX_PHOTO_BYTES:
        method, field = "sendPhoto", "photo"
    elif kind == "audio" and mime in VOICE_MIMES:
        method, field = "sendVoice", "voice"
    elif kind == "video" and mime == "video/mp4":
        method, field = "sendVideo", "video"
    else:
        method, field = "sendDocument", "document"
    name = filename or default_filename(mime)
    result = await call(token, method, data={"chat_id": chat_id}, files={field: (name, data, mime)}, timeout=60)
    return _message_id(chat_id, result)


def default_filename(mime: str) -> str:
    extension = {
        "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
        "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "video/mp4": "mp4",
        "application/pdf": "pdf",
    }.get(mime, "bin")
    return f"attachment.{extension}"


async def download(token: str, file_id: str) -> bytes:
    """The bytes of a file a contact sent, refused above Telegram's own ceiling."""
    info = await call(token, "getFile", data={"file_id": file_id})
    if not isinstance(info, dict) or not info.get("file_path"):
        raise HTTPException(502, "Telegram did not return the file.")
    if int(info.get("file_size") or 0) > MAX_DOWNLOAD_BYTES:
        raise HTTPException(413, "The file exceeds the 20 MB Telegram allows a bot to download.")
    url = f"{API_BASE}/file/bot{token}/{info['file_path']}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise HTTPException(502, f"The file could not be downloaded from Telegram (HTTP {response.status_code}).")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > MAX_DOWNLOAD_BYTES:
                        raise HTTPException(413, "The file exceeds the 20 MB Telegram allows a bot to download.")
                    data.extend(chunk)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"The file could not be downloaded from Telegram ({type(exc).__name__}).") from None
    if not data:
        raise HTTPException(502, "Telegram returned an empty file.")
    return bytes(data)


# --- text shaping ---------------------------------------------------------------
#
# Agents write Markdown. Telegram renders its own HTML subset and shows anything
# else literally, so the stored Markdown is converted for the copy that is sent.

_FENCE = re.compile(r"```[^\n`]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)\"<>]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.DOTALL)
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[*+]\s+", re.MULTILINE)


def markdown_to_telegram_html(text: str) -> str:
    """Best-effort Markdown to Telegram HTML. Code is set aside first, so
    nothing inside it is read as formatting."""
    if not text:
        return text
    kept: list[str] = []

    def keep(fragment: str) -> str:
        kept.append(fragment)
        return f"\x00{len(kept) - 1}\x00"

    work = _FENCE.sub(lambda match: keep(f"<pre>{html.escape(match.group(1).rstrip(), quote=False)}</pre>"), text)
    work = _INLINE_CODE.sub(lambda match: keep(f"<code>{html.escape(match.group(1), quote=False)}</code>"), work)
    work = _LINK.sub(lambda match: keep(
        f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1), quote=False)}</a>'), work)
    work = html.escape(work, quote=False)
    work = _HEADING.sub(r"<b>\1</b>", work)
    work = _BULLET.sub(r"\1• ", work)
    work = _BOLD.sub(r"<b>\1</b>", work)
    work = _BOLD_ALT.sub(r"<b>\1</b>", work)
    work = _STRIKE.sub(r"<s>\1</s>", work)
    work = _ITALIC.sub(r"<i>\1</i>", work)
    return re.sub(r"\x00(\d+)\x00", lambda match: kept[int(match.group(1))], work)


def strip_markdown(text: str) -> str:
    """The reply without markup, for when Telegram refuses the formatted one."""
    work = _FENCE.sub(lambda match: match.group(1), text or "")
    work = _INLINE_CODE.sub(r"\1", work)
    work = _LINK.sub(r"\1 (\2)", work)
    work = _HEADING.sub(r"\1", work)
    work = _BULLET.sub(r"\1• ", work)
    for pattern in (_BOLD, _BOLD_ALT, _STRIKE, _ITALIC):
        work = pattern.sub(r"\1", work)
    return work
