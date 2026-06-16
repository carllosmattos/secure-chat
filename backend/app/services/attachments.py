from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass

from security_patterns import apply_policy, detect, redact_text
from security_patterns.file_guard import block_reason_for_filename

from app.config import settings

try:
    import magic
except ImportError:
    magic = None  # type: ignore[assignment]


SENSITIVE_MAGIC_PREFIXES = (
    b"-----BEGIN",
)

IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"})
DOCUMENT_MIMES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
    }
)


@dataclass
class AttachmentResult:
    filename: str
    extracted_text: str = ""
    blocked: bool = False
    block_reason: str | None = None
    pii_redacted: bool = False


def _detect_mime(content: bytes, filename: str) -> str:
    if magic:
        try:
            return magic.from_buffer(content, mime=True)
        except Exception:
            pass
    _, ext = os.path.splitext(filename.lower())
    ext_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return ext_map.get(ext, "application/octet-stream")


def _extract_pdf(content: bytes) -> str:
    import pdfplumber

    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
    return "\n".join(texts)


def _extract_docx(content: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_image_ocr(content: bytes) -> str:
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(content))
    return pytesseract.image_to_string(image)


def _scan_extracted_text(text: str) -> tuple[str, bool, str | None]:
    findings = detect(text)
    policy = apply_policy(findings)
    if policy.block:
        return text, True, "; ".join(policy.reasons)
    redacted, _ = redact_text(text)
    return redacted, False, None


async def process_attachment(filename: str, content: bytes) -> AttachmentResult:
    if len(content) > settings.max_attachment_bytes:
        return AttachmentResult(
            filename,
            blocked=True,
            block_reason=f"File exceeds {settings.max_attachment_bytes} bytes",
        )

    reason = block_reason_for_filename(filename)
    if reason:
        return AttachmentResult(filename, blocked=True, block_reason=reason)

    if content.startswith(SENSITIVE_MAGIC_PREFIXES):
        return AttachmentResult(
            filename,
            blocked=True,
            block_reason="PEM/certificate content detected in file",
        )

    mime = _detect_mime(content, filename)
    loop = asyncio.get_event_loop()

    try:
        if mime in DOCUMENT_MIMES or mime == "application/octet-stream":
            _, ext = os.path.splitext(filename.lower())
            if mime == "application/pdf" or ext == ".pdf":
                text = await loop.run_in_executor(None, _extract_pdf, content)
            elif "wordprocessingml" in mime or ext == ".docx":
                text = await loop.run_in_executor(None, _extract_docx, content)
            elif ext in (".txt", ".csv") or mime.startswith("text/"):
                text = content.decode("utf-8", errors="replace")
            else:
                return AttachmentResult(filename, blocked=False)
        elif mime in IMAGE_MIMES:
            text = await asyncio.wait_for(
                loop.run_in_executor(None, _extract_image_ocr, content),
                timeout=settings.ocr_timeout_seconds,
            )
        else:
            return AttachmentResult(
                filename,
                blocked=True,
                block_reason=f"Unsupported file type: {mime}",
            )
    except asyncio.TimeoutError:
        return AttachmentResult(filename, blocked=True, block_reason="OCR timeout")
    except Exception as exc:
        return AttachmentResult(filename, blocked=True, block_reason=f"Extraction failed: {exc}")

    if not text.strip():
        return AttachmentResult(filename)

    redacted, blocked, block_reason = _scan_extracted_text(text)
    return AttachmentResult(
        filename,
        extracted_text=redacted,
        blocked=blocked,
        block_reason=block_reason,
        pii_redacted=redacted != text,
    )


async def process_attachments(files: list[tuple[str, bytes]]) -> list[AttachmentResult]:
    if len(files) > settings.max_attachments:
        return [
            AttachmentResult(
                "batch",
                blocked=True,
                block_reason=f"Max {settings.max_attachments} attachments allowed",
            )
        ]
    return [await process_attachment(name, data) for name, data in files]
