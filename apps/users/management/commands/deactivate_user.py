"""
Management command to deactivate a user account (GDPR erasure / abuse response).

Admins (or support staff with shell access) can disable any account directly,
bypassing the password-confirmation step of the self-service endpoint. This is
the enforcement path for confirmed GDPR deletion requests and policy violations.

Usage:
    manage.py deactivate_user --email user@example.com --reason "GDPR erasure request"
    manage.py deactivate_user --pk <uuid> --reason "Spam account"
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Deactivate a user account (set is_active=False) by email or primary key."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, help="Email address of the user to deactivate.")
        parser.add_argument("--pk", type=str, help="Primary key (UUID) of the user to deactivate.")
        parser.add_argument(
            "--reason",
            type=str,
            default="",
            help="Reason for deactivation (recorded in the audit trail).",
        )

    def handle(self, *args, **options):
        email = options.get("email")
        pk = options.get("pk")

        if bool(email) == bool(pk):
            raise CommandError("Provide exactly one of --email or --pk.")

        try:
            user = User.objects.get(email=email) if email else User.objects.get(pk=pk)
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found for {email or pk}.") from exc

        if not user.is_active:
            self.stdout.write(self.style.WARNING(f"User {user.email} is already deactivated."))
            return

        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        # Revoke all outstanding refresh tokens for the account.
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        self.stdout.write(self.style.SUCCESS(f"Deactivated user {user.email} (pk={user.pk})."))
        if options["reason"]:
            self.stdout.write(f"Reason: {options['reason']}")
