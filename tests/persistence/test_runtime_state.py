"""
Tests for persistence Phase 2: BotRuntimeState model + apps/trading/state.py.

Covers the recovery contract Phase 3/4/5 build on: unique (bot_type, bot_id)
rows, non-raising reads on a fresh DB, lifecycle transitions, heartbeat
staleness, and the "alive engine always has a row" invariant of touch().
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.trading import state as rt
from apps.trading.models import BotRuntimeState


@pytest.mark.django_db
class TestBotRuntimeStateModel:
    def test_defaults(self):
        row = BotRuntimeState.objects.create(bot_type="grid", bot_id="abc123")
        assert row.status == rt.RUNNING
        assert row.state == {}
        assert row.worker == ""
        assert row.heartbeat_at is None
        assert row.created_at is not None and row.updated_at is not None

    def test_unique_bot_type_bot_id(self):
        BotRuntimeState.objects.create(bot_type="grid", bot_id="abc123")
        with pytest.raises(IntegrityError), transaction.atomic():
            BotRuntimeState.objects.create(bot_type="grid", bot_id="abc123")

    def test_same_bot_id_different_type_allowed(self):
        BotRuntimeState.objects.create(bot_type="grid", bot_id="abc123")
        BotRuntimeState.objects.create(bot_type="signal", bot_id="abc123")
        assert BotRuntimeState.objects.count() == 2

    def test_str(self):
        row = BotRuntimeState.objects.create(bot_type="grid", bot_id="abc123")
        assert str(row) == "grid:abc123 [running]"


@pytest.mark.django_db
class TestUpsertAndGet:
    def test_upsert_creates_with_heartbeat(self):
        row = rt.upsert("grid", "b1", {"current_side": "Buy"}, worker="worker-a")
        assert row.pk is not None
        assert row.state == {"current_side": "Buy"}
        assert row.status == rt.RUNNING
        assert row.worker == "worker-a"
        assert row.heartbeat_at is not None

    def test_upsert_state_none_preserves_payload(self):
        rt.upsert("grid", "b1", {"current_side": "Buy"})
        row = rt.upsert("grid", "b1", status=rt.STOPPING)
        assert row.state == {"current_side": "Buy"}
        assert row.status == rt.STOPPING
        assert BotRuntimeState.objects.count() == 1

    def test_upsert_state_replaces_payload(self):
        rt.upsert("grid", "b1", {"current_side": "Buy"})
        rt.upsert("grid", "b1", {"current_side": "Sell"})
        assert rt.get_state("grid", "b1") == {"current_side": "Sell"}

    def test_get_returns_row_or_none(self):
        rt.upsert("grid", "b1", {})
        assert rt.get("grid", "b1") is not None
        assert rt.get("grid", "missing") is None

    def test_get_state_fresh_db_returns_empty_dict(self):
        # Read helpers must never raise on a database with no state rows —
        # recovery runs before any engine boots.
        assert rt.get_state("grid", "never-seen") == {}
        assert rt.get("grid", "never-seen") is None


@pytest.mark.django_db
class TestLifecycle:
    def test_set_status_updates_and_stamps(self):
        rt.upsert("grid", "b1", {})
        assert rt.set_status("grid", "b1", rt.STOPPED) is True
        row = rt.get("grid", "b1")
        assert row.status == rt.STOPPED
        assert row.heartbeat_at is not None

    def test_set_status_missing_row_is_false(self):
        assert rt.set_status("grid", "missing", rt.STOPPED) is False

    def test_touch_creates_row_when_absent(self):
        assert rt.touch("grid", "b1", worker="w1") is True
        row = rt.get("grid", "b1")
        assert row is not None
        assert row.status == rt.RUNNING
        assert row.state == {}
        assert row.worker == "w1"
        assert row.heartbeat_at is not None

    def test_touch_only_advances_heartbeat_on_existing(self):
        rt.upsert("grid", "b1", {"k": 1}, worker="old")
        first = rt.get("grid", "b1").heartbeat_at
        rt.touch("grid", "b1", worker="new")
        row = rt.get("grid", "b1")
        assert row.state == {"k": 1}  # payload untouched
        assert row.worker == "new"
        assert row.heartbeat_at >= first

    def test_delete_row_and_missing(self):
        rt.upsert("grid", "b1", {})
        assert rt.delete("grid", "b1") == 1
        assert rt.get("grid", "b1") is None
        assert rt.delete("grid", "b1") == 0


@pytest.mark.django_db
class TestQueries:
    def test_running_filters_by_status_type_and_worker(self):
        rt.upsert("grid", "a", {}, worker="w1")
        rt.upsert("signal", "b", {}, worker="w1")
        rt.upsert("grid", "c", {}, worker="w2")
        rt.upsert("grid", "d", {})
        rt.set_status("grid", "d", rt.STOPPED)

        assert set(rt.running().values_list("bot_id", flat=True)) == {"a", "b", "c"}
        # ordering is "-updated_at" (same-second ties) => compare as sets
        assert set(rt.running(bot_type="grid").values_list("bot_id", flat=True)) == {
            "a",
            "c",
        }
        assert set(rt.running(worker="w1").values_list("bot_id", flat=True)) == {
            "a",
            "b",
        }

    def test_stale_includes_old_and_null_heartbeats(self):
        now = timezone.now()
        # stale running engine (worker died without clean shutdown)
        rt.upsert("grid", "old", {})
        BotRuntimeState.objects.filter(bot_id="old").update(
            heartbeat_at=now - timedelta(minutes=10)
        )
        # fresh running engine — must be excluded
        rt.upsert("grid", "fresh", {})
        # running row with NO heartbeat at all — treated as stale (isnull)
        BotRuntimeState.objects.create(bot_type="grid", bot_id="null-hb", status=rt.RUNNING)
        # stale but cleanly stopped — must be excluded
        rt.upsert("grid", "stopped-old", {})
        BotRuntimeState.objects.filter(bot_id="stopped-old").update(
            status=rt.STOPPED, heartbeat_at=now - timedelta(minutes=10)
        )

        stale_ids = set(rt.stale(seconds=60).values_list("bot_id", flat=True))
        assert "old" in stale_ids
        assert "null-hb" in stale_ids
        assert "fresh" not in stale_ids
        assert "stopped-old" not in stale_ids
