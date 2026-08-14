"""
Fix UserBalance timestamp fields to match the current TimeStampedModel.

The original migration used django_extensions fields (created/modified).
TimeStampedModel now provides created_at/updated_at. This migration
renames the columns in-place and updates the Django migration state.

PURE PYTHON - NO DJANGO IMPORTS

Since Django's makemigrations cannot auto-detect renames of fields
that originated from a different package (django_extensions vs core),
this migration is written manually.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE users_balances RENAME COLUMN created TO created_at",
                    reverse_sql="ALTER TABLE users_balances RENAME COLUMN created_at TO created",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE users_balances RENAME COLUMN modified TO updated_at",
                    reverse_sql="ALTER TABLE users_balances RENAME COLUMN updated_at TO modified",
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="userbalance",
                    name="created",
                ),
                migrations.RemoveField(
                    model_name="userbalance",
                    name="modified",
                ),
                migrations.AddField(
                    model_name="userbalance",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True),
                ),
                migrations.AddField(
                    model_name="userbalance",
                    name="updated_at",
                    field=models.DateTimeField(auto_now=True),
                ),
                migrations.AlterField(
                    model_name="userbalance",
                    name="id",
                    field=models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
        ),
    ]
