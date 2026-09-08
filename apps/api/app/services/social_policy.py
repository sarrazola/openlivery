"""Reply permissions shared by every UI and the background sender."""
from datetime import timedelta

from fastapi import HTTPException

from ..models import Conversation, now_utc

SOCIAL_PROVIDERS = {"instagram", "messenger"}
CAPABILITIES = {"text": True, "image": True, "audio": True, "video": True, "file": True,
                "reactions": False, "quotes": False, "templates": False}


def window_fields(conversation: Conversation) -> dict:
    channel = conversation.social_channel
    last = conversation.social_last_inbound_at
    until = last + timedelta(hours=24) if last else None
    approved = bool(channel and channel.human_agent_enabled)
    if approved and channel.connection_source == "managed":
        from .social_connections import get_app_config
        approved = get_app_config(channel.provider).human_agent_enabled
    human_until = last + timedelta(days=7) if last and approved else until
    now = now_utc()
    reason = None
    if channel and channel.is_enabled and channel.status == "reauthorization_required":
        reason = "authorization_expired"
    elif not channel or not channel.is_enabled or channel.status != "connected":
        reason = "channel_disconnected"
    elif channel.token_expires_at and channel.token_expires_at <= now:
        reason = "authorization_expired"
    elif not conversation.social_thread_owned:
        reason = "another_app_controls_conversation"
    elif conversation.status == "resolved":
        reason = "conversation_resolved"
    allowed = reason is None
    standard_open = bool(allowed and until and now < until)
    human_open = bool(allowed and human_until and now < human_until)
    if not reason and not (human_open if conversation.mode == "human" else standard_open):
        reason = "reply_window_closed"
    return {
        "reply_window_until": until, "reply_window_open": standard_open,
        "human_reply_window_until": human_until, "human_reply_window_open": human_open,
        "reply_block_reason": reason, "channel_capabilities": CAPABILITIES.copy(),
    }


def require_reply(conversation: Conversation, *, human: bool) -> bool:
    """Return whether a real human reply needs the approved Human Agent tag."""
    fields = window_fields(conversation)
    if not fields["human_reply_window_open" if human else "reply_window_open"]:
        reasons = {
            "channel_disconnected": "Reconnect this channel before replying.",
            "authorization_expired": "The channel authorization expired. Reconnect the account.",
            "another_app_controls_conversation": "Another messaging application controls this conversation.",
            "conversation_resolved": "This conversation is resolved.",
            "reply_window_closed": "The reply window is closed. Wait for a new message from this person.",
        }
        raise HTTPException(status_code=409, detail=reasons.get(fields["reply_block_reason"], "Replies are unavailable."))
    if not human and conversation.mode != "ai":
        raise HTTPException(status_code=409, detail="A human operator took control of this conversation.")
    return human and not fields["reply_window_open"]
