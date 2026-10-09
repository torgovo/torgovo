"""
Subscriptions app configuration
"""

from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    verbose_name = "Telegram Signals Subscriptions"

    def ready(self):
        # A15: wire post_save/post_delete receivers that invalidate the
        # plan-endpoint caches whenever plan data changes.
        from apps.subscriptions import signals  # noqa: F401
