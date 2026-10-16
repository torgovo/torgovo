# G1 / FR A2: admin-driven Model C plan fields.
# Schema only — the Model C seed rows are created by the idempotent
# management command ``seed_model_c_plans`` (run at deploy / from admin),
# NOT here: test databases pre-created plan rows with these slugs, so an
# automatic data migration would collide with them.
#
# Added admin-editable fields: description, sort_order, bot_types, market,
# max_signals_per_month, max_exchanges. Display order now = sort_order.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0008_rename_quantumaideposit_investordeposit"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="description",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="sort_order",
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="bot_types",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="market",
            field=models.CharField(
                choices=[("spot", "Spot only"), ("spot_futures", "Spot + Futures")],
                default="spot",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="max_signals_per_month",
            field=models.PositiveIntegerField(default=10),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="max_exchanges",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterModelOptions(
            name="subscriptionplan",
            options={"ordering": ["sort_order", "price_monthly"]},
        ),
    ]
