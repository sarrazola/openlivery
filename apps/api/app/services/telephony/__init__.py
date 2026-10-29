"""Phone calls: the agency's ElevenLabs workspace (voice, speech recognition,
turn taking) and its phone carriers (Twilio, Telnyx), reached with its own keys."""


class TelephonyError(RuntimeError):
    """A provider refused a request; the message is fit to show the operator."""
