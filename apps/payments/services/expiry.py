"""
Subscription expiry lifecycle (G4 / FR A6) — BotSubscription only.

State machine (computed LIVE from dates, never trusted from a stale
status column; the daily beat task only persists status="expired" for
bookkeeping/listing):

  status != "active"          → "inactive"      (pending/rejected/cancelled/…)
  now <= expires_at           → "active"        (full access)
  expires_at < now <= grace   → "grace"         (still FULL access — A6)
  now > grace_until           → "hard_stopped"  (no new bot entries; open
                                                 positions are never touched)

A6 hard rule: hard stop blocks CREATION of new bots only. Existing bots
and open positions keep running.
"""

import logging

from django.utils import timezone

from apps.payments.models import BotSubscription

logger = logging.getLogger(__name__)


def subscription_state(sub: BotSubscription, now=None) -> str:
    """Return the live lifecycle state of a BotSubscription."""
    if sub.status != "active":
        return "inactive"
    now = now or timezone.now()
    if not sub.expires_at:
        # Legacy rows approved before G4 have no clock → treat as active
        # (no expiry data means no basis to stop anything).
        return "active"
    if now <= sub.expires_at:
        return "active"
    # Past expires_at: still in grace if grace_until has not passed.
    # Rows approved before G4 have grace_until=None → fall back to
    # expires_at itself (hard stop immediately, no grace invented).
    if sub.grace_until and now <= sub.grace_until:
        return "grace"
    return "hard_stopped"


def is_hard_stopped(sub: BotSubscription, now=None) -> bool:
    """True when the subscription must refuse new bot entries."""
    return subscription_state(sub, now) == "hard_stopped"


def get_usable_subscription(user, bot_type: str):
    """Return an active (or in-grace) BotSubscription for user+bot_type.

    Returns None when: no active row exists, OR the row is hard-stopped.
    Grace-period rows ARE usable (A6: full access retained during grace).
    Callers raise their existing "No active … subscription" error on None.
    """
    sub = (
        BotSubscription.objects.filter(user=user, plan__bot_type=bot_type, status="active")
        .select_related("plan")
        .first()
    )
    if not sub or is_hard_stopped(sub):
        return None
    return sub


def transition_expired_subscriptions(now=None) -> int:
    """Persist status="expired" for hard-stopped rows (bookkeeping).

    The gate already enforces hard stop via live date math, so this is not
    the security boundary — it keeps admin listings/filters honest and
    stops the reminder task from re-scanning long-dead rows.
    Returns the number of rows transitioned.
    """
    now = now or timezone.now()
    qs = BotSubscription.objects.filter(status="active").exclude(expires_at=None)
    count = 0
    # (user_id, sub_pk, slug) of Model C rows that actually flipped this pass
    # — consumed by the profile fallback below.
    model_c_expired = []
    for sub in qs.iterator():
        if is_hard_stopped(sub, now):
            # Adversarial review 2026-10-15 (CRITICAL): compare-and-swap.
            # A stale save() here could clobber an approve() that re-stamped
            # this row between our read and write, locking a paying user out
            # (gate filters status="active") until manual intervention.
            # status alone does NOT guard (approve() also leaves status
            # "active") — pin expires_at too: approve() rewrites the clock,
            # so a changed expires_at makes this UPDATE match 0 rows.
            # .update() bypasses auto_now → refresh updated_at explicitly.
            flipped = BotSubscription.objects.filter(
                pk=sub.pk, status="active", expires_at=sub.expires_at
            ).update(status="expired", updated_at=timezone.now())
            count += flipped
            # FR A2 / Q15: remember flipped Model C rows (plan chain is still
            # on the in-memory sub — .update() does not touch it).
            if flipped and sub.plan.subscription_plan_id:
                model_c_expired.append((sub.user_id, sub.pk, sub.plan.subscription_plan.slug))
    # FR A2 / Q15 downgrade rule: the profile drops to free only when the
    # expired tier governs it (profile slug == expired slug) AND no other
    # usable Model C sub remains. Upgrades were applied at approve(); this is
    # the single place a downgrade lands. Legacy profiles are never touched.
    if model_c_expired:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        for user_id, sub_pk, slug in model_c_expired:
            others = (
                BotSubscription.objects.filter(
                    user_id=user_id,
                    status="active",
                    plan__subscription_plan__isnull=False,
                )
                .exclude(pk=sub_pk)
                .select_related("plan")
            )
            # Grace counts as usable (full access per A6) — only a second
            # hard stop would leave the user with no Model C tier at all.
            if any(not is_hard_stopped(o, now) for o in others):
                continue
            user = User.objects.filter(pk=user_id).first()
            if user is None or user.subscription_plan != slug:
                continue
            user.subscription_plan = "free"
            user.save(update_fields=["subscription_plan", "max_bots_allowed"])
    if count:
        logger.info("G4: transitioned %d subscription(s) to expired", count)
    return count
