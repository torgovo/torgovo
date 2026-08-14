import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "Created"),
                            ("update", "Updated"),
                            ("delete", "Deleted"),
                            ("login", "Login"),
                            ("logout", "Logout"),
                            ("password_change", "Password Changed"),
                            ("api_key_change", "API Key Changed"),
                            ("bot_start", "Bot Started"),
                            ("bot_stop", "Bot Stopped"),
                            ("deposit", "Deposit"),
                            ("withdrawal", "Withdrawal"),
                            ("trade", "Trade Executed"),
                        ],
                        max_length=20,
                    ),
                ),
                ("resource_type", models.CharField(max_length=50)),
                ("resource_id", models.CharField(blank=True, max_length=50)),
                ("old_values", models.JSONField(blank=True, null=True)),
                ("new_values", models.JSONField(blank=True, null=True)),
                ("description", models.TextField()),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
            ],
            options={
                "db_table": "core_audit_log",
            },
        ),
        migrations.CreateModel(
            name="SystemConfiguration",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("key", models.CharField(max_length=100, unique=True)),
                ("value", models.TextField()),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "core_system_configuration",
            },
        ),
        migrations.CreateModel(
            name="UserActivityLog",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("action", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("endpoint", models.CharField(blank=True, max_length=255)),
                ("method", models.CharField(blank=True, max_length=10)),
                ("status_code", models.IntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "core_user_activity_log",
            },
        ),
        migrations.AddField(
            model_name="useractivitylog",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="activity_logs",
                to="users.customuser",
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to="users.customuser",
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["user", "created_at"], name="core_audit_log_user_id_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["action", "created_at"], name="core_audit_log_action_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["resource_type", "resource_id"], name="core_audit_log_resource_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(
                fields=["user", "created_at"], name="core_activity_log_user_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(
                fields=["action", "created_at"], name="core_activity_log_action_created_idx"
            ),
        ),
    ]
