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


async def _run_ffmpeg(args: list[str], stdin_data: bytes | None = None) -> bytes | None:
    """Run ffmpeg returning stdout, or None when it fails or times out."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(process.communicate(stdin_data), timeout=FFMPEG_TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return None
    if process.returncode != 0 or not out:
        return None
    return out


async def to_whatsapp_voice(data: bytes, mime: str) -> tuple[bytes, str]:
    """Transcode audio bytes to ogg/opus. Best-effort: returns the input
    unchanged when it is already ogg or when ffmpeg is unavailable/fails.

    Two passes on purpose: MediaRecorder's fragmented mp4 carries a non-zero
    start offset and micro-gaps between fragments. Transcoded directly to ogg
    (with or without timestamp filters), Meta accepts the upload but drops the
    message at delivery as application/octet-stream (error 131053), or ships a
    voice note phones cannot download. Bouncing through WAV discards the source
    timeline entirely, and the ogg encoded from it delivers and plays."""
    base_mime = (mime or "").split(";")[0].strip().lower()
    if base_mime == "audio/ogg" or not shutil.which("ffmpeg"):
        return data, mime
    wav = await _run_ffmpeg(["-i", "pipe:0", "-vn", "-f", "wav", "pipe:1"], data)
    if wav is None:
        return data, mime
    out = await _run_ffmpeg(
        ["-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1"],
        wav,
    )
    if out is None:
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
