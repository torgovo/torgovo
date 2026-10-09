"""
Payments app configuration
"""

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    verbose_name = "Payment Processing"

    def ready(self):
        # A15: wire post_save/post_delete receivers that invalidate the
        # plan-endpoint caches whenever plan data changes.
        from apps.payments import signals  # noqa: F401
