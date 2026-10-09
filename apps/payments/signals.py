"""
Signal receivers for the payments app.

A15: ``subscription_plans_v1`` (bot-plans listing) was never invalidated on
plan changes — up to 1 h stale.  Saving/deleting a SubscriptionPlan now
drops both plan-endpoint cache keys (same invalidation set as the
subscriptions app).
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.payments.models import SubscriptionPlan

PLAN_CACHE_KEYS = ("telegram_plans_v1", "subscription_plans_v1")


@receiver(post_save, sender=SubscriptionPlan)
@receiver(post_delete, sender=SubscriptionPlan)
def invalidate_plan_caches(sender, **kwargs):
    """Drop cached plan listings after any SubscriptionPlan write."""
    for key in PLAN_CACHE_KEYS:
        cache.delete(key)
