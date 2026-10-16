"""
Signal receivers for the subscriptions app.

A15: both plan-endpoint caches are invalidated whenever plan data changes,
replacing the old subscribe-time ``cache.delete("telegram_plans_v1")`` (an
event that cannot change plan data) and closing the gap where
``subscription_plans_v1`` was never invalidated at all.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.subscriptions.models import TelegramSignalPlan

# All keys are dropped on any plan save/delete: each cache only holds plan
# payloads, so a full flush is cheap (next request rebuilds it in 1 query)
# and it covers cross-effects (shared serializer/route changes) for free.
# v1 kept in the set for one release so any pre-upgrade stale entry dies too.
PLAN_CACHE_KEYS = ("telegram_plans_v1", "subscription_plans_v1", "subscription_plans_v2")


@receiver(post_save, sender=TelegramSignalPlan)
@receiver(post_delete, sender=TelegramSignalPlan)
def invalidate_plan_caches(sender, **kwargs):
    """Drop cached plan listings after any TelegramSignalPlan write."""
    for key in PLAN_CACHE_KEYS:
        cache.delete(key)
