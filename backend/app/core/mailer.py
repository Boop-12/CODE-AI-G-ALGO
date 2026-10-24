import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import settings

logger = logging.getLogger("gnkalgo.mail")


def action_url(page: str, token: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/{page}?token={quote(token)}"


def _send_sync(recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = recipient
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


async def deliver_link(recipient: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST:
        logger.warning("Email delivery is unavailable because SMTP_HOST is not configured")
        return False
    if not settings.SMTP_FROM and not settings.SMTP_USER:
        raise RuntimeError("Email delivery requires SMTP_FROM or SMTP_USER")
    try:
        await asyncio.to_thread(_send_sync, recipient, subject, body)
    except (OSError, smtplib.SMTPException) as error:
        logger.error("Email delivery failed (%s)", type(error).__name__)
        return False
    return True
