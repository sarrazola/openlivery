"""Files the agent can send: a per-agent library of images and documents.

Not knowledge. Nothing here is read, chunked or indexed; a product photo has
no text to learn from. What the business wants is for the agent to *send* the
file at the right moment, so each entry carries a name and a short description
of when it applies, and the agent gets one built-in tool, ``send_file``, whose
choices are those names. The handler hands the bytes to the tool loop, which
delivers them the way files from HTTP tools already leave: as message
attachments through the conversation's channel.

Images are normalized once, on upload: resized to ``MAX_IMAGE_SIDE`` and
re-encoded as JPEG (PNG when the image has transparency). WebP is not an
option here even though it is smaller: the WhatsApp Cloud API accepts it only
for stickers and Instagram messaging rejects it, so one stored JPEG or PNG is
what every channel takes. Documents are stored as uploaded.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, AgentMediaAsset
from .tool_files import ToolFile
from .tools.specs import ToolSpec

# Every name and description rides inside the tool the model sees on each
# reply, so the library stays small on purpose.
MAX_MEDIA_ASSETS = 30
MAX_NAME_CHARS = 80
MAX_DESCRIPTION_CHARS = 300
# Input limits. An image is re-encoded, so the stored copy is far smaller; a
# document is stored as is, under the limit the knowledge upload already uses.
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILE_UPLOAD_BYTES = 20 * 1024 * 1024
# The longest side after normalization, and the JPEG quality. Enough for a
# product photo on a phone screen, a few hundred KB at most.
MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 82

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
FILE_MIMES = {"application/pdf"}
_EXTENSION_MIMES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    ".pdf": "application/pdf",
}

TOOL_NAME = "send_file"

# LLM-facing rules, in the language of the agent's prompt like the rest of it.
_RULES = {
    "es": (
        "ARCHIVOS DEL NEGOCIO: dispones de la herramienta send_file para enviar al cliente, como adjunto en este "
        "chat, uno de los archivos del negocio (fotos de productos, catálogos, listas de precios). Cada archivo "
        "tiene un nombre y una nota de cuándo enviarlo. Úsala cuando el cliente pida ver algo que uno de ellos "
        "muestra o cuando su nota diga que corresponde; envía solo los que vengan al caso, de a uno salvo que pida "
        "varios, y no repitas uno que ya enviaste en la conversación.\n"
        "Solo existen los archivos de la lista: no prometas ni describas otros. Al enviar uno, acompáñalo con una "
        "frase corta y natural en tu respuesta; el archivo llega por separado, no pegues enlaces ni lo describas "
        "como si fuera texto."
    ),
    "en": (
        "BUSINESS FILES: you have the send_file tool to send the customer one of the business's files (product "
        "photos, catalogs, price lists) as an attachment on this chat. Each file has a name and a note on when to "
        "send it. Use it when the customer asks to see something one of them shows or when its note says it "
        "applies; send only the ones that fit, one at a time unless they ask for several, and do not resend one "
        "you already sent in this conversation.\n"
        "Only the listed files exist: do not promise or describe others. When you send one, add a short, natural "
        "sentence in your reply; the file arrives on its own, so do not paste links or describe it as text."
    ),
}


@dataclass
class MediaValidationError(Exception):
    """Why an upload was refused; the router turns it into an HTTP status."""

    status_code: int
    detail: str


@dataclass
class NormalizedUpload:
    data: bytes
    mime: str
    filename: str
    kind: str


_MAGIC = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def guess_mime(content_type: str | None, filename: str | None, data: bytes = b"") -> str:
    """The upload's type: what the browser said, else the extension, else the
    first bytes (a browser sends ``application/octet-stream`` for a file it
    does not know, and a phone may drop the extension)."""
    mime = (content_type or "").lower().split(";")[0].strip()
    if mime in IMAGE_MIMES or mime in FILE_MIMES:
        return mime
    by_extension = _EXTENSION_MIMES.get(PurePath(filename or "").suffix.lower())
    if by_extension:
        return by_extension
    for magic, sniffed in _MAGIC:
        if data.startswith(magic):
            return sniffed
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return mime or "application/octet-stream"


def upload_limit(mime: str) -> int:
    return MAX_IMAGE_UPLOAD_BYTES if mime in IMAGE_MIMES else MAX_FILE_UPLOAD_BYTES


def normalize_upload(data: bytes, mime: str, filename: str | None) -> NormalizedUpload:
    """Validate and normalize an upload for the library.

    Images come back resized and re-encoded; documents come back untouched
    with a filename that carries the right extension."""
    if mime in IMAGE_MIMES:
        return _normalize_image(data, filename)
    if mime in FILE_MIMES:
        return NormalizedUpload(data=data, mime=mime, filename=_with_extension(filename, ".pdf", "document"), kind="file")
    raise MediaValidationError(400, "Only images (JPEG, PNG, WebP, GIF) and PDF files can be added to the library")


def _normalize_image(data: bytes, filename: str | None) -> NormalizedUpload:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            # Phone photos carry their rotation in EXIF; bake it in, since the
            # channels show the pixels as stored.
            image = ImageOps.exif_transpose(image) or image
            transparent = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
            image = image.convert("RGBA" if transparent else "RGB")
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
            out = BytesIO()
            if transparent:
                image.save(out, format="PNG", optimize=True)
                mime, extension = "image/png", ".png"
            else:
                image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
                mime, extension = "image/jpeg", ".jpg"
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        # A truncated file raises OSError; an image that claims an absurd
        # size raises DecompressionBombError, a ValueError.
        raise MediaValidationError(400, "The image could not be read. Check that the file is not damaged.") from exc
    return NormalizedUpload(data=out.getvalue(), mime=mime, filename=_with_extension(filename, extension, "image"), kind="image")


def _with_extension(filename: str | None, extension: str, fallback: str) -> str:
    stem = PurePath((filename or "").strip()).stem
    safe = "".join(ch if ch.isalnum() or ch in "._ -" else "_" for ch in stem).strip(" .")[:200]
    return f"{safe or fallback}{extension}"


def media_prompt(agent: Agent) -> str:
    return _RULES[agent.prompt_language if agent.prompt_language in _RULES else "es"]


def build_media_spec(db: Session, agent: Agent) -> ToolSpec | None:
    """The ``send_file`` tool for this agent, or None when its library is empty.

    The names and descriptions are read now, once per reply; the bytes only
    when the model actually sends a file. Each file goes out at most once per
    reply, however many times the model asks for it."""
    rows = db.execute(
        select(AgentMediaAsset.id, AgentMediaAsset.name, AgentMediaAsset.description, AgentMediaAsset.mime, AgentMediaAsset.filename)
        .where(AgentMediaAsset.agent_id == agent.id)
        .order_by(AgentMediaAsset.created_at)
    ).all()
    if not rows:
        return None
    by_name = {row.name: row for row in rows}
    sent: set[str] = set()

    def handler(args: dict) -> tuple[str, bool, list[ToolFile]]:
        name = str(args.get("name") or "").strip()
        row = by_name.get(name) or next((r for r in rows if r.name.casefold() == name.casefold()), None)
        if row is None:
            return f"Unknown file '{name}'. The files you can send are: " + ", ".join(by_name), True, []
        if row.name in sent:
            return f"'{row.name}' was already sent in this reply; do not send it again.", False, []
        data = db.scalar(select(AgentMediaAsset.data).where(AgentMediaAsset.id == row.id))
        if data is None:
            return f"'{row.name}' is no longer available.", True, []
        sent.add(row.name)
        return (
            f"'{row.name}' ({row.filename}) is being delivered to the customer as an attachment on this chat. "
            "Confirm it in a short sentence; do not describe its contents or paste a link.",
            False,
            [ToolFile(data=data, mime=row.mime, filename=row.filename)],
        )

    listing = "\n".join(f"- {row.name}" + (f": {row.description}" if row.description else "") for row in rows)
    return ToolSpec(
        name=TOOL_NAME,
        description=(
            "Send one of the business's files to the customer as an attachment on this chat. "
            "Files available, with when to send each:\n" + listing
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The exact name of the file to send", "enum": list(by_name)},
            },
            "required": ["name"],
        },
        handler=handler,
    )
