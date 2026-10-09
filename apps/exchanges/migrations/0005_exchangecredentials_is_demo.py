# Generated manually — adds is_demo field to ExchangeCredentials

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exchanges", "0004_alter_exchangecredentials_exchange_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="exchangecredentials",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Use demo trading (simulated funds, real API keys). "
                    "Distinct from testnet which uses separate testnet API keys."
                ),
            ),
        ),
    ]
