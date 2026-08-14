"""
Management command: migrate_legacy_tables

Copies data from old (pre-refactor) table names to the new table layout
and drops the legacy tables.

Run AFTER ``manage.py migrate`` on a database that was previously running
the triple-duplication model layout.

Legacy → new mapping:
  exchanges_exchangestatus        → investments_exchange_status
  exchanges_supportedblockchains  → investments_supported_blockchains
  exchanges_exchangerates         → investments_exchange_rates
  trading_exchangestatus          → investments_exchange_status
  trading_supportedblockchains    → investments_supported_blockchains
  trading_exchangerates           → investments_exchange_rates
  investments_exchange            (dropped — duplicate, schema differs)
  investments_trading_pair        (dropped — duplicate, schema differs)
  investments_exchangecredentials (dropped — duplicate, schema differs)
"""

from django.core.management.base import BaseCommand
from django.db import connection

LEGACY_MAP = [
    {
        "src": "exchanges_exchangestatus",
        "dst": "investments_exchange_status",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "exchange_name",
            "status",
            "response_time_ms",
            "last_check",
            "error_message",
            "api_limits",
        ],
    },
    {
        "src": "exchanges_supportedblockchains",
        "dst": "investments_supported_blockchains",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "name",
            "blockchain_code",
            "native_coin",
            "explorer_url",
            "confirmation_blocks",
            "transaction_fee_type",
            "average_fee",
            "is_active",
        ],
    },
    {
        "src": "exchanges_exchangerates",
        "dst": "investments_exchange_rates",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "from_currency",
            "to_currency",
            "rate",
            "exchange_name",
            "source",
            "timestamp",
        ],
    },
    {
        "src": "trading_exchangestatus",
        "dst": "investments_exchange_status",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "exchange_name",
            "status",
            "response_time_ms",
            "last_check",
            "error_message",
            "api_limits",
        ],
    },
    {
        "src": "trading_supportedblockchains",
        "dst": "investments_supported_blockchains",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "name",
            "blockchain_code",
            "native_coin",
            "explorer_url",
            "confirmation_blocks",
            "transaction_fee_type",
            "average_fee",
            "is_active",
        ],
    },
    {
        "src": "trading_exchangerates",
        "dst": "investments_exchange_rates",
        "columns": [
            "id",
            "created_at",
            "updated_at",
            "from_currency",
            "to_currency",
            "rate",
            "exchange_name",
            "source",
            "timestamp",
        ],
    },
]

STALE_TABLES = [
    "investments_exchange",
    "investments_trading_pair",
    "investments_exchangecredentials",
    "investments_botconfiguration",
    "exchanges_exchangestatus",
    "exchanges_supportedblockchains",
    "exchanges_exchangerates",
    "trading_exchangestatus",
    "trading_supportedblockchains",
    "trading_exchangerates",
]


class Command(BaseCommand):
    help = "Migrate data from legacy (pre-refactor) tables to the new layout"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            existing = self._list_tables(cursor)
            self._migrate_tables(cursor, existing)
            self._drop_stale_tables(cursor, existing)

    def _list_tables(self, cursor):
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        return {row[0] for row in cursor.fetchall()}

    def _migrate_tables(self, cursor, existing):
        for mapping in LEGACY_MAP:
            src = mapping["src"]
            dst = mapping["dst"]
            cols = ", ".join(mapping["columns"])

            if src not in existing:
                self.stdout.write(f"  SKIP {src} (table does not exist)")
                continue
            if dst not in existing:
                self.stdout.write(
                    f"  SKIP {src} → {dst} (target does not exist — run migrate first)"
                )
                continue

            cursor.execute(f"SELECT COUNT(*) FROM {src}")
            count = cursor.fetchone()[0]
            if count == 0:
                self.stdout.write(f"  SKIP {src} (empty)")
                continue

            cursor.execute(
                f"""
                INSERT INTO {dst} ({cols})
                SELECT {cols} FROM {src}
                ON CONFLICT DO NOTHING
            """
            )
            self.stdout.write(f"  OK   {src} → {dst} ({count} rows)")

    def _drop_stale_tables(self, cursor, existing):
        for table in STALE_TABLES:
            if table in existing:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                self.stdout.write(f"  DROP {table}")
