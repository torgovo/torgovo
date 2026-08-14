"""
Management command to re-encrypt all credentials with a new Fernet key.

Usage:
    # Re-encrypt using old key from argument (if FERNET_KEY was already rotated)
    python manage.py reencrypt_credentials --old-key <old_fernet_key>

    # Dry-run: show what would change without saving
    python manage.py reencrypt_credentials --old-key <old_fernet_key> --dry-run
"""

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("management")


class Command(BaseCommand):
    help = "Re-encrypt ExchangeCredentials and QuantumAIFund keys with current FERNET_KEY"

    def add_arguments(self, parser):
        parser.add_argument("--old-key", required=True, help="Previous FERNET_KEY value")
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")

    def _reencrypt_exchange_creds(self, old_fernet, new_fernet, dry_run):
        from apps.exchanges.models import ExchangeCredentials

        count = 0
        errors = 0
        for cred in ExchangeCredentials.objects.all():
            try:
                old_keys = cred.get_decrypted_credentials()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Cannot decrypt {cred.id}: {e}"))
                errors += 1
                continue
            if dry_run:
                self.stdout.write(f"  Would re-encrypt ExchangeCredentials {cred.id} ({cred.user})")
            else:
                from core.utils import encrypt_message

                for field in ["api_key", "secret_key", "passphrase"]:
                    if getattr(cred, field):
                        setattr(cred, field, encrypt_message(old_keys.get(field, "")).decode())
                cred.save(update_fields=["api_key", "secret_key", "passphrase"])
                self.stdout.write(f"  Re-encrypted ExchangeCredentials {cred.id} ({cred.user})")
            count += 1
        return count, errors

    def _reencrypt_quantum_funds(self, old_fernet, new_fernet, dry_run):
        from apps.bots.models import QuantumAIFund

        count = 0
        errors = 0
        for fund in QuantumAIFund.objects.all():
            try:
                old_keys = fund.get_decrypted_credentials()
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  Cannot decrypt QuantumAIFund {fund.id}: {e}")
                )
                errors += 1
                continue
            if dry_run:
                self.stdout.write(f"  Would re-encrypt QuantumAIFund {fund.id} ({fund.name})")
            else:
                from core.utils import encrypt_message

                for field in ["master_api_key", "master_secret_key", "master_passphrase"]:
                    raw = getattr(fund, field)
                    if raw and old_keys.get(field.replace("master_", "")):
                        setattr(
                            fund,
                            field,
                            encrypt_message(old_keys[field.replace("master_", "")]).decode(),
                        )
                fund.save()
                self.stdout.write(f"  Re-encrypted QuantumAIFund {fund.id} ({fund.name})")
            count += 1
        return count, errors

    def handle(self, *args, **options):
        old_key = options["old_key"]
        dry_run = options["dry_run"]

        from cryptography.fernet import Fernet
        from django.conf import settings

        try:
            old_fernet = Fernet(old_key.encode() if not old_key.endswith("=") else old_key.encode())
        except Exception as e:
            raise CommandError(f"Invalid old key: {e}")

        try:
            new_fernet = Fernet(
                settings.FERNET_KEY.encode()
                if not settings.FERNET_KEY.endswith("=")
                else settings.FERNET_KEY.encode()
            )
        except Exception as e:
            raise CommandError(f"Current FERNET_KEY invalid: {e}")

        self.stdout.write(f"Re-encrypting credentials {'(dry-run)' if dry_run else ''}...")
        self.stdout.write(f"  Old key: {old_key[:10]}...{old_key[-10:]}")
        self.stdout.write(f"  New key: {settings.FERNET_KEY[:10]}...{settings.FERNET_KEY[-10:]}")

        ec_count, ec_errors = self._reencrypt_exchange_creds(old_fernet, new_fernet, dry_run)
        qf_count, qf_errors = self._reencrypt_quantum_funds(old_fernet, new_fernet, dry_run)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {ec_count} ExchangeCredentials, {qf_count} QuantumAIFunds re-encrypted "
                f"({ec_errors + qf_errors} errors)"
            )
        )
