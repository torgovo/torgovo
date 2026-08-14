"""
Investment App Configuration
"""

from django.apps import AppConfig


class InvestmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.investments"
    verbose_name = "Investment Management"

    def ready(self):
        # Import signals when app is ready
        try:
            import apps.investments.signals  # noqa: F401  (side-effect: signal registration)
        except ImportError:
            pass
