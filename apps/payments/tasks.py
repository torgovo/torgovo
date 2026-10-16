"""
Periodic tasks for the payments app (G4 / FR A6 expiry lifecycle).

Routed to the "payments" queue by config/celery.py task_routes.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.payments.models import BotSubscription
from apps.payments.services.expiry import is_hard_stopped, transition_expired_subscriptions
from core.email import send_email

logger = logging.getLogger(__name__)


def _reminder_offsets():
    """Admin-configured day-offsets before expiry (default 7,5,3,1)."""
    return sorted(settings.SUBSCRIPTION_REMINDER_OFFSET_DAYS, reverse=True)


def _send_expiry_reminder(sub: BotSubscription, days_left: int) -> bool:
    """Send one D-N email and record it in the idempotency ledger.

    Returns True only when the email was delivered AND the ledger stamped
    (callers count it towards the run's reminders_sent).
    """
    subject = f"Torgovo subscription expires in {days_left} day(s)"
    message = (
        f"Hi {sub.user.get_username()},\n\n"
        f"Your {sub.plan.name} subscription expires on "
        f"{sub.expires_at:%Y-%m-%d %H:%M UTC}.\n\n"
        f"After expiry you keep full access for a {settings.SUBSCRIPTION_GRACE_PERIOD_DAYS}-day "
        "grace period, after which no new bots can be created (open positions keep running).\n\n"
        "Renew in the dashboard to keep uninterrupted access.\n\n"
        "— Torgovo"
    )
    ok = send_email(subject, message, [sub.user.email])
    if not ok:
        # Ledger stamp happens ONLY on success — a transient SMTP outage
        # retries on the next daily run (offset still due, key not written).
        return False
    # Adversarial review 2026-10-15 (WARNING): guarded read-modify-write.
    # Re-read the ledger under row lock before stamping so an approve()
    # (which clears the dict) between our email send and this write cannot
    # be overwritten with the stale pre-approve ledger content.
    with transaction.atomic():
        row = BotSubscription.objects.select_for_update().get(pk=sub.pk)
        ledger = dict(row.expiry_reminders_sent or {})
        ledger[f"D-{days_left}"] = timezone.now().isoformat()
        row.expiry_reminders_sent = ledger
        row.save(update_fields=["expiry_reminders_sent", "updated_at"])
    logger.info(
        "G4: expiry reminder D-%d sent to %s (sub %s)",
        days_left,
        sub.user.email,
        sub.id,
    )
    return True


@shared_task(name="apps.payments.tasks.check_subscription_expiry")
def check_subscription_expiry() -> dict:
    """Daily expiry sweep (FR A6).

    1. Persist status="expired" for rows past their grace window.
    2. Send D-N reminder emails (once per offset per paid term).

    Reminder cadence is exactly the offsets in SUBSCRIPTION_REMINDER_OFFSET_DAYS
    (default D-7/5/3/1) — A6 mandates no "grace started" notice, so none is sent
    when the grace window opens (the D-1 reminder is the follow-through).
    """
    now = timezone.now()
    expired_count = transition_expired_subscriptions(now)
    reminders_sent = 0

    offsets = _reminder_offsets()
    # Candidate set: active rows with a clock, not yet hard-stopped.
    qs = (
        BotSubscription.objects.filter(status="active")
        .exclude(expires_at=None)
        .select_related("user", "plan")
    )
    for sub in qs.iterator():
        if is_hard_stopped(sub, now):
            continue
        days_left = (sub.expires_at.date() - now.date()).days
        if days_left not in offsets:
            continue
        if f"D-{days_left}" in (sub.expiry_reminders_sent or {}):
            continue  # idempotent: already emailed for this term
        if _send_expiry_reminder(sub, days_left):
            reminders_sent += 1

    result = {"expired": expired_count, "reminders_sent": reminders_sent}
    logger.info("check_subscription_expiry: %s", result)
    return result
