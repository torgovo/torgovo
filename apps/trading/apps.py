from django.apps import AppConfig


class TradingConfig(AppConfig):
    """Django app configuration for the trading app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trading'
    verbose_name = 'Trading'

    def ready(self):
        """Import signals when app is ready."""
        pass
