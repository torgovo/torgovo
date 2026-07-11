"""
Management command to encrypt any plaintext QuantumAIFund master keys.

Run against production after deploying the model save() override:
    python manage.py encrypt_quantum_fund_keys --dry-run   # preview only
    python manage.py encrypt_quantum_fund_keys              # encrypt

The model's save() already auto-encrypts on write, but existing rows
that were created before the override was deployed may still have
plaintext values. This command finds and re-saves every row so the
save() override fires.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from core.utils import looks_encrypted


class Command(BaseCommand):
    help = "Encrypt plaintext QuantumAIFund master API keys"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which funds would be affected without making changes',
        )

    def handle(self, *args, **options):
        from apps.bots.models import QuantumAIFund
        from cryptography.fernet import Fernet

        if not settings.FERNET_KEY:
            raise CommandError("FERNET_KEY is not configured — cannot encrypt")

        try:
            Fernet(settings.FERNET_KEY.encode())
        except Exception as e:
            raise CommandError(f"FERNET_KEY is invalid: {e}")

        dry_run = options['dry-run']
        affected = 0
        plaintext_fields = 0

        for fund in QuantumAIFund.objects.all():
            # Check all three key fields: look for values that aren't empty
            # and don't already look Fernet-encrypted.
            fields_to_check = {
                'master_api_key': fund.master_api_key,
                'master_secret_key': fund.master_secret_key,
                'master_passphrase': fund.master_passphrase,
            }

            dirty = False
            for field_name, value in fields_to_check.items():
                if value and not looks_encrypted(value):
                    dirty = True
                    plaintext_fields += 1
                    self.stdout.write(
                        f"  [plaintext] {fund.name}.{field_name} "
                        f"(length={len(value)})"
                    )

            if dirty:
                affected += 1
                if not dry_run:
                    # Calling fund.save() triggers the model's save()
                    # override which calls looks_encrypted() + encrypt_api_key()
                    # on each key field before writing to the database.
                    fund.save()

        summary = (
            f"Found {affected} fund(s) with {plaintext_fields} plaintext field(s)"
        )
        if dry_run and affected > 0:
            summary += " — use without --dry-run to encrypt"
        elif affected == 0:
            summary += " — all keys already encrypted"

        if affected > 0:
            if dry_run:
                self.stdout.write(self.style.WARNING(summary))
            else:
                self.stdout.write(self.style.SUCCESS(summary + " — encrypted"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
