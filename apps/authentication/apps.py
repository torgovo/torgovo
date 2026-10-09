"""
Authentication app configuration for Torgovo Crypto Trading Platform
"""

import os

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "Authentication"

    def ready(self):
        """Import signals when app is ready."""
        import apps.authentication.signals  # noqa: F401  (side-effect: signal registration)

        # SEC-1: Fail-closed boot check — Google OAuth requires a client ID.
        # Without this, the audience validation in GoogleAuthSerializer is
        # bypassed entirely (any Google token from any app is accepted).
        # Skip during tests (pytest sets this env var).
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            from decouple import config as decouple_config

            google_client_id = decouple_config("GOOGLE_CLIENT_ID", default="")
            if not google_client_id:
                raise ImproperlyConfigured(
                    "GOOGLE_CLIENT_ID is not set. Google OAuth authentication will "
                    "accept tokens from ANY application. Set GOOGLE_CLIENT_ID in "
                    "your .env file."
                )
