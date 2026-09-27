"""Assemble the report email and send it via SMTP (or write it to the outbox in dry-run mode)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .config import Settings
from .photos import attachment_jpeg
from .report import Draft, body, subject

MAX_TOTAL_BYTES = 15 * 1024 * 1024


def build_message(draft: Draft, settings: Settings, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{settings.reporter_name} <{settings.reporter_email}>"
    msg["To"] = to
    msg["Cc"] = settings.reporter_email  # keep a copy as proof of submission
    msg["Subject"] = subject(draft)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.reporter_email.rpartition("@")[2] or None)
    msg.set_content(body(draft, settings))

    total = 0
    for i, photo in enumerate(draft.photos, start=1):
        data = attachment_jpeg(Path(photo))
        if total + len(data) > MAX_TOTAL_BYTES:
            data = attachment_jpeg(Path(photo), max_edge=1600, quality=75)
        total += len(data)
        msg.add_attachment(
            data, maintype="image", subtype="jpeg", filename=f"{draft.id}_foto{i}.jpg"
        )
    if total > MAX_TOTAL_BYTES:
        raise ValueError(f"Attachments total {total // 1024 // 1024} MB; send fewer photos.")
    return msg


def deliver(msg: EmailMessage, settings: Settings, draft_id: str) -> str:
    """Send the message, or save it as .eml when DRY_RUN is on. Returns a description of what happened."""
    if settings.dry_run:
        path = settings.outbox / f"{draft_id}.eml"
        path.write_bytes(bytes(msg))
        return f"dry_run: saved to {path} (set DRY_RUN=0 in .env to send for real)"

    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=60) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=60) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    return f"sent to {msg['To']} (cc {msg['Cc']})"
