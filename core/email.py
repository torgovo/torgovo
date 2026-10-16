"""
Single email delivery helper (FR Part B Q22).

Delivery order:
  1. SMTP — Django's configured EMAIL_BACKEND (console backend in dev,
     SMTP in production, locmem in tests).
  2. Resend HTTP API — only if RESEND_API_KEY is set AND SMTP raised.
     Resend is the fallback, never the primary.

Callers (background tasks, auth flows) should never let a delivery error
break their main flow: this helper logs failures and returns bool instead
of raising.
"""

import logging

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_email(subject: str, message: str, recipient_list, html_message=None) -> bool:
    """Send one email to a list of recipients. Returns True on success.

    Never raises. SMTP first; on exception, falls back to Resend if an API
    key is configured. Both failing → error is logged, False returned.
    """
    if not recipient_list:
        logger.warning("send_email: empty recipient_list, dropping subject=%r", subject)
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@torgovo.com")

    # --- Primary: SMTP via Django's configured EMAIL_BACKEND ---
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=list(recipient_list),
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.warning("SMTP delivery failed (%s), trying Resend fallback", exc)

    # --- Fallback: Resend HTTP API (skipped if no key) ---
    api_key = getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        logger.error(
            "send_email: SMTP failed and no RESEND_API_KEY set — email lost. subject=%r",
            subject,
        )
        return False

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": list(recipient_list),
                "subject": subject,
                "text": message,
                **({"html": html_message} if html_message else {}),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        # Last resort failed too — log loudly, still never raise.
        logger.error("send_email: Resend fallback also failed (%s). subject=%r", exc, subject)
        return False
