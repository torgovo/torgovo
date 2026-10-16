"""
Signal receivers for the payments app.

A15: ``subscription_plans_v1`` (bot-plans listing) was never invalidated on
plan changes — up to 1 h stale.  Saving/deleting a SubscriptionPlan now
drops both plan-endpoint cache keys (same invalidation set as the
subscriptions app).

G2 / FR A3: ``sync_payment_code_status`` mirrors an admin approve/reject
decision onto the linked PaymentCode (CODE_STATUS_BY_SUB_STATUS).  Loaded
from PaymentsConfig.ready() — every model below is registered by then.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.payments.models import BotSubscription, PaymentCode, SubscriptionPlan
from apps.subscriptions.models import TelegramSubscription

# v1 kept in the set for one release so any pre-upgrade stale entry dies too.
PLAN_CACHE_KEYS = ("telegram_plans_v1", "subscription_plans_v1", "subscription_plans_v2")

# Subscription status → PaymentCode status (G2). Any other status
# (pending_payment / pending_approval) leaves the code untouched.
CODE_STATUS_BY_SUB_STATUS = {
    "active": "approved",
    "rejected": "rejected",
}


@receiver(post_save, sender=SubscriptionPlan)
@receiver(post_delete, sender=SubscriptionPlan)
def invalidate_plan_caches(sender, **kwargs):
    """Drop cached plan listings after any SubscriptionPlan write."""
    for key in PLAN_CACHE_KEYS:
        cache.delete(key)


@receiver(post_save, sender=BotSubscription)
@receiver(post_save, sender=TelegramSubscription)
def sync_payment_code_status(sender, instance, **kwargs):
    """Keep PaymentCode.status in lockstep with its downstream subscription."""
    if instance._state.adding:
        return
    target = CODE_STATUS_BY_SUB_STATUS.get(instance.status)
    if target is None:
        return
    PaymentCode.objects.filter(subscription_id=str(instance.id)).exclude(status=target).update(
        status=target
    )
