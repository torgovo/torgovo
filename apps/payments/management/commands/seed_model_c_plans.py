"""
Idempotent seeder for the Model C subscription plans (FR A2 / grill-me).

Run at deploy (and any time the canonical prices need re-asserting):

    python manage.py seed_model_c_plans
    python manage.py seed_model_c_plans --dry-run

Creates the 5 canonical rows by slug; on re-run it upserts only the Model C
spec fields (prices, sort order, limits) and never touches name/slug of
custom rows. All values below are the LOCKED grill-me decisions (Q6 matrix).
Paid tiers open signal/grid/martingale; quantum_ai is always exempt from the
bot_types gate. Plan data is DB-driven — this seed only establishes it.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from apps.payments.models import SubscriptionPlan

# slug, name, monthly, yearly, sort, max_bots, bot_types, market, signals/mo, exchanges, description
# Q6 matrix locked via grill-me (2026-10-17): paid tiers open signal/grid/martingale;
# quantum_ai always exempt from the bot_types gate (Q2 decision).
MODEL_C = [
    (
        "free",
        "Free",
        "0.00",
        "0.00",
        10,
        1,
        ["signal"],
        "spot",
        10,
        1,
        "10 signals/mo, 1 bot, 1 exchange, spot only",
    ),
    (
        "basic",
        "Basic",
        "15.00",
        "144.00",
        20,
        3,
        ["signal", "grid", "martingale"],
        "spot",
        50,
        3,
        "",
    ),
    (
        "standard",
        "Standard",
        "25.00",
        "240.00",
        30,
        5,
        ["signal", "grid", "martingale"],
        "spot",
        300,
        6,
        "",
    ),
    (
        "premium",
        "Premium",
        "49.00",
        "470.40",
        40,
        10,
        ["signal", "grid", "martingale"],
        "spot",
        1500,
        15,
        "",
    ),
    (
        "creator",
        "Creator",
        "20.00",
        "192.00",
        50,
        5,
        ["signal", "grid", "martingale"],
        "spot",
        100,
        3,
        "Includes referral cash commissions (FR A7)",
    ),
]

# Fields re-asserted on every run for canonical slugs
SPEC_FIELDS = (
    "price_monthly",
    "price_yearly",
    "sort_order",
    "max_bots_allowed",
    "bot_types",
    "market",
    "max_signals_per_month",
    "max_exchanges",
    "is_active",
)


class Command(BaseCommand):
    help = "Create/update the 5 Model C subscription plans (FR A2, idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without writing.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        created = updated = unchanged = 0

        for row in MODEL_C:
            (
                slug,
                name,
                monthly,
                yearly,
                sort,
                max_bots,
                bot_types,
                market,
                signals,
                exchanges,
                desc,
            ) = row
            defaults = {
                "name": name,
                "description": desc,
                "price_monthly": Decimal(monthly),
                "price_yearly": Decimal(yearly),
                "sort_order": sort,
                "max_bots_allowed": max_bots,
                "max_webhooks_allowed": 10,
                "bot_types": bot_types,
                "market": market,
                "max_signals_per_month": signals,
                "max_exchanges": exchanges,
                "features": [],
                "is_active": True,
                "trial_days": 0,
            }

            plan = SubscriptionPlan.objects.filter(slug=slug).first()
            if plan is None:
                if not dry:
                    try:
                        SubscriptionPlan.objects.create(slug=slug, **defaults)
                    except IntegrityError:
                        # unique name collision with a non-canonical slug row
                        self.stderr.write(
                            f"SKIP {slug}: a different plan already uses name '{name}' "
                            "— resolve the name conflict in admin, then re-run."
                        )
                        continue
                self.stdout.write(f"CREATE {slug}: ${monthly}/mo")
                created += 1
                continue

            changes = {f: defaults[f] for f in SPEC_FIELDS if getattr(plan, f) != defaults[f]}
            if not changes:
                unchanged += 1
                continue
            self.stdout.write(
                f"UPDATE {slug}: " + ", ".join(f"{f}={v}" for f, v in changes.items())
            )
            if not dry:
                for f, v in changes.items():
                    setattr(plan, f, v)
                plan.save()
            updated += 1

        prefix = "[dry-run] " if dry else ""
        counts = f"{created} created, {updated} updated, {unchanged} unchanged"
        self.stdout.write(self.style.SUCCESS(f"{prefix}Model C plans: {counts}"))
