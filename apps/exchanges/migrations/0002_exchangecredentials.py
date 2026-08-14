# Generated manually — adds ExchangeCredentials (depends on users for the FK)

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exchanges", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExchangeCredentials",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "exchange_name",
                    models.CharField(
                        choices=[
                            ("binance", "Binance"),
                            ("bybit", "Bybit"),
                            ("okx", "OKX"),
                            ("mexc", "MEXC"),
                            ("alpaca", "Alpaca"),
                        ],
                        max_length=20,
                    ),
                ),
                ("api_key", models.TextField(help_text="Encrypted API key")),
                ("secret_key", models.TextField(help_text="Encrypted secret key")),
                (
                    "passphrase",
                    models.TextField(
                        blank=True,
                        help_text="Encrypted passphrase (required for some exchanges)",
                        null=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "is_testnet",
                    models.BooleanField(default=True, help_text="Use testnet/sandbox mode"),
                ),
                (
                    "permissions",
                    models.JSONField(
                        default=dict, help_text="Trading permissions (spot, futures, margin, etc.)"
                    ),
                ),
                ("last_verified", models.DateTimeField(blank=True, null=True)),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("verified", "Verified"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("trading_enabled", models.BooleanField(default=True)),
                ("withdrawal_enabled", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exchanges_credentials",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "exchanges_credentials",
                "indexes": [
                    models.Index(
                        fields=["user", "exchange_name"], name="exchanges_c_user_id_f81d25_idx"
                    ),
                    models.Index(fields=["is_active"], name="exchanges_c_is_acti_d66c83_idx"),
                    models.Index(
                        fields=["verification_status"], name="exchanges_c_verific_a468b7_idx"
                    ),
                ],
                "unique_together": {("user", "exchange_name")},
            },
        ),
    ]
