# Generated manually: add last_heartbeat to bot models for stale-bot detection

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bots", "0006_quantumaibot_signalbot_remove_order_custom_bot_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="gridbot",
            name="last_heartbeat",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="martingalebot",
            name="last_heartbeat",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="quantumaibot",
            name="last_heartbeat",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
