# Generated manually: add ReserveTransaction model for audit trail

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('bots', '0007_add_last_heartbeat'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReserveTransaction',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount', models.DecimalField(decimal_places=8, max_digits=20)),
                ('balance_before', models.DecimalField(decimal_places=8, max_digits=20)),
                ('balance_after', models.DecimalField(decimal_places=8, max_digits=20)),
                ('transaction_type', models.CharField(choices=[
                    ('top_up', 'Admin Top-Up'),
                    ('withdrawal', 'Admin Withdrawal'),
                    ('shortfall_cover', 'Shortfall Cover (paid to users)'),
                    ('excess_deposit', 'Excess Return Deposit (from overperformance)'),
                    ('smoothing_adj', 'Smoothing Adjustment'),
                ], max_length=30)),
                ('description', models.TextField(blank=True)),
                ('fund', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reserve_transactions', to='bots.quantumaifund')),
                ('reserve', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='bots.reservefund')),
            ],
            options={
                'verbose_name': 'Reserve Transaction',
                'verbose_name_plural': 'Reserve Transactions',
                'db_table': 'bots_reserve_transactions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='reservetransaction',
            index=models.Index(fields=['fund', '-created_at'], name='bots_reserv_fund_id_7b030d_idx'),
        ),
        migrations.AddIndex(
            model_name='reservetransaction',
            index=models.Index(fields=['transaction_type'], name='bots_reserv_transac_20791c_idx'),
        ),
    ]
