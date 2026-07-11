import uuid

from django.db import migrations, models


def gen_uuid(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    for row in CustomUser.objects.all():
        row.webhook_token = uuid.uuid4()
        row.save(update_fields=['webhook_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_remove_customuser_is_verified_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='webhook_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text='Token used to authenticate webhook calls from TradingView',
                null=True,
            ),
        ),
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customuser',
            name='webhook_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                help_text='Token used to authenticate webhook calls from TradingView',
            ),
        ),
    ]
