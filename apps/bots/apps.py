"""
Bots app configuration
"""

from django.apps import AppConfig


class BotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bots"
    verbose_name = "Trading Bots"

    def ready(self):
        import apps.bots.signals  # noqa: F401
