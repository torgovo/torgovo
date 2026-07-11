"""
Authentication app configuration for Torgovo Crypto Trading Platform
"""
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = 'Authentication'

    def ready(self):
        """Import signals when app is ready."""
        import apps.authentication.signals