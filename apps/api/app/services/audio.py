"""Audio transcoding for outbound WhatsApp delivery.

Browsers record voice notes as webm/opus (Chrome) or mp4/aac (Safari), but
WhatsApp only plays voice messages encoded as ogg/opus — anything else shows
"this audio is no longer available" on the recipient's phone. The stored
attachment keeps the original (browser-friendly) bytes; only the copy sent
through a WhatsApp channel is transcoded.
"""

import asyncio
import os
import shutil
import tempfile

FFMPEG_TIMEOUT = 60


async def to_whatsapp_voice(data: bytes, mime: str) -> tuple[bytes, str]:
    """Transcode audio bytes to ogg/opus. Best-effort: returns the input
    unchanged when it is already ogg or when ffmpeg is unavailable/fails."""
    base_mime = (mime or "").split(";")[0].strip().lower()
    if base_mime == "audio/ogg" or not shutil.which("ffmpeg"):
        return data, mime
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-vn", "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
            "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(process.communicate(data), timeout=FFMPEG_TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return data, mime
    if process.returncode != 0 or not out:
        return data, mime
    return out, "audio/ogg"


async def audio_duration_seconds(data: bytes) -> int | None:
    """Duration of an audio payload in whole seconds (WhatsApp requires it to
    render voice notes on iOS). Best-effort: None when ffprobe is unavailable.

    ffprobe needs a real file: ogg duration lives in the last page, which is
    unreachable on a non-seekable pipe."""
    if not shutil.which("ffprobe"):
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as handle:
            handle.write(data)
            path = handle.name
        process = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(process.communicate(), timeout=15)
        return max(1, round(float(out.decode().strip())))
    except (OSError, asyncio.TimeoutError, ValueError):
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
