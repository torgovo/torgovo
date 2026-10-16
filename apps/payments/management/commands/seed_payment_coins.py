"""
Idempotent seeder for the G2 / FR A3 payment coin list.

Run at deploy (and any time the canonical launch set needs re-asserting):

    python manage.py seed_payment_coins
    python manage.py seed_payment_coins --dry-run

Launch set = USDT on TRC20 / BEP20 / ERC20 (FR A3).  Addresses are NOT
invented here — deposit_address stays blank until an admin sets the real
on-chain receive address; quotes fail with 400 until then.  Re-runs upsert
only is_active/sort_order for these three canonical rows and never touch
custom coins.
"""

from django.core.management.base import BaseCommand

from apps.payments.models import PaymentCoin

# coin, chain, sort_order (USDT-TRC20 first: cheapest network for users)
LAUNCH_COINS = [
    ("USDT", "TRC20", 10),
    ("USDT", "BEP20", 20),
    ("USDT", "ERC20", 30),
]


class Command(BaseCommand):
    help = "Seed/refresh the canonical payment coin list (USDT on TRC20/BEP20/ERC20)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without writing")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        for coin, chain, sort in LAUNCH_COINS:
            obj, created = PaymentCoin.objects.get_or_create(
                coin=coin,
                chain=chain,
                defaults={"sort_order": sort, "is_active": True},
            )
            if not created:
                changed = False
                if obj.sort_order != sort:
                    obj.sort_order = sort
                    changed = True
                if not obj.is_active:
                    obj.is_active = True
                    changed = True
                if changed and not dry:
                    obj.save(update_fields=["sort_order", "is_active", "updated_at"])
                action = "would-update" if dry else ("updated" if changed else "unchanged")
            else:
                action = "would-create" if dry else "created"
                if dry:
                    obj.delete()  # dry-run: get_or_create already wrote it — undo
            self.stdout.write(f"  {action:12} {coin} on {chain}")

        total = PaymentCoin.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done ({'dry-run, ' if dry else ''}{total} coin rows total — "
                "set deposit_address in admin before enabling quotes)"
            )
        )
