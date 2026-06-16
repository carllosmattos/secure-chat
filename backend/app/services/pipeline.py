from __future__ import annotations

import hashlib
import uuid
from collections import Counter

from security_patterns import apply_policy, detect, redact_text
from security_patterns.file_guard import block_reason_for_filename, is_sensitive_filename
from security_patterns.patterns import Profile

from app.config import settings
from app.services.attachments import AttachmentResult, process_attachments
from app.services.vault import merge_mappings, vault


class PipelineBlockError(Exception):
    def __init__(self, reasons: list[str], findings_summary: list[str]):
        self.reasons = reasons
        self.findings_summary = findings_summary
        super().__init__("; ".join(reasons))


class PipelineResult:
    def __init__(
        self,
        redacted_text: str,
        mapping: dict[str, str],
        pii_redacted: bool,
        attachment_names: list[str],
        pii_counts: dict[str, int],
        prompt_hash: str,
    ):
        self.redacted_text = redacted_text
        self.mapping = mapping
        self.pii_redacted = pii_redacted
        self.attachment_names = attachment_names
        self.pii_counts = pii_counts
        self.prompt_hash = prompt_hash


def _hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _finding_summary(findings) -> list[str]:
    counts = Counter(f.label for f in findings)
    return [f"{label} ({count})" for label, count in counts.items()]


async def process_message_pipeline(
    session_id: uuid.UUID,
    message_text: str,
    files: list[tuple[str, bytes]],
    profile: Profile | None = None,
) -> PipelineResult:
    profile = profile or settings.security_profile  # type: ignore[assignment]

    for filename, _ in files:
        reason = block_reason_for_filename(filename)
        if reason:
            raise PipelineBlockError([reason], [reason])

    attachment_results: list[AttachmentResult] = await process_attachments(files)
    for ar in attachment_results:
        if ar.blocked:
            raise PipelineBlockError([ar.block_reason or "Attachment blocked"], [ar.block_reason or "blocked"])

    combined_text = message_text
    all_mappings: list[dict[str, str]] = []
    attachment_names: list[str] = []

    for ar in attachment_results:
        attachment_names.append(ar.filename)
        if ar.extracted_text:
            combined_text += f"\n\n[Attachment: {ar.filename}]\n{ar.extracted_text}"

    findings = detect(combined_text)
    policy = apply_policy(findings, profile)

    if policy.block:
        raise PipelineBlockError(policy.reasons, _finding_summary(findings))

    redacted, mapping = redact_text(combined_text, profile)
    all_mappings.append(mapping)

    full_mapping = merge_mappings(*all_mappings)
    vault.store(session_id, full_mapping)

    pii_counts = Counter(f.kind for f in findings if f.severity == "redact")

    return PipelineResult(
        redacted_text=redacted,
        mapping=full_mapping,
        pii_redacted=bool(full_mapping),
        attachment_names=attachment_names,
        pii_counts=dict(pii_counts),
        prompt_hash=_hash_prompt(redacted),
    )
