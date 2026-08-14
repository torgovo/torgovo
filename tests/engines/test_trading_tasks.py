"""
Tests for the Celery task layer in apps/trading/tasks.py.

Covers the full task surface:
- run_trading_bot (the @shared_task(bind=True) executor with dedup + retry)
- start_bot / stop_bot (state flips)
- check_all_active_bots (dispatch loop)
- check_stale_bots / _handle_stale_bot (heartbeat recovery)
- heartbeat_check
- reset_monthly_signal_limits
- accrue_quantum_ai_profits / distribute_quantum_ai_profits / _credit_reserve

Invocation note: bind=True tasks receive the task itself as ``self``, so
tests push a fake request id via push_request() then call .run() directly.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from apps.trading import tasks as trade_tasks

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grid_bot(user, **overrides):
    from apps.bots.models import GridBot

    defaults = dict(
        user=user,
        bot_name="Grid Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        base_amount=Decimal("100"),
        favor_levels=3,
        against_levels=3,
    )
    defaults.update(overrides)
    return GridBot.objects.create(**defaults)


def _martingale_bot(user, subscription, **overrides):
    from apps.bots.models import MartingaleBot

    defaults = dict(
        user=user,
        subscription=subscription,
        bot_name="Martingale Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        base_amount=Decimal("100"),
        favor_levels=3,
        against_levels=3,
    )
    defaults.update(overrides)
    return MartingaleBot.objects.create(**defaults)


def _signal_bot(user, **overrides):
    from apps.bots.models import SignalBot

    defaults = dict(
        user=user,
        bot_name="Signal Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        default_amount=Decimal("10"),
    )
    defaults.update(overrides)
    return SignalBot.objects.create(**defaults)


def _quantum_bot(fund, **overrides):
    from apps.bots.models import QuantumAIBot

    defaults = dict(
        fund=fund,
        bot_name="Quantum Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
    )
    defaults.update(overrides)
    return QuantumAIBot.objects.create(**defaults)


def _run_task(task, task_id="task-1", **kwargs):
    """Push a fake request id onto a bind=True task and run it."""
    task.push_request(id=task_id)
    try:
        return task.run(**kwargs)
    finally:
        task.pop_request()


# ---------------------------------------------------------------------------
# run_trading_bot
# ---------------------------------------------------------------------------


class TestRunTradingBot:
    def test_success_forwards_run_bot_result(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=True))):
            with patch(
                "apps.trading.engines.execution.run_bot",
                return_value={"success": True, "mode": "new", "signal": "entry", "side": "buy"},
            ) as mock_run:
                result = _run_task(
                    run_trading_bot,
                    bot_id="11111111-1111-1111-1111-111111111111",
                    bot_type="grid",
                )

        assert result == {"success": True, "mode": "new", "signal": "entry", "side": "buy"}
        mock_run.assert_called_once_with(
            "11111111-1111-1111-1111-111111111111",
            bot_type="grid",
            restore_mode=False,
        )

    def test_restore_mode_passed_to_engine(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=True))):
            with patch(
                "apps.trading.engines.execution.run_bot",
                return_value={"success": True, "mode": "restore"},
            ) as mock_run:
                _run_task(
                    run_trading_bot,
                    bot_id="11111111-1111-1111-1111-111111111111",
                    bot_type="martingale",
                    restore_mode=True,
                )

        mock_run.assert_called_once_with(
            "11111111-1111-1111-1111-111111111111",
            bot_type="martingale",
            restore_mode=True,
        )

    def test_dedup_guard_returns_duplicate_error(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=False))):
            with patch("apps.trading.engines.execution.run_bot") as mock_run:
                result = _run_task(
                    run_trading_bot,
                    bot_id="11111111-1111-1111-1111-111111111111",
                    bot_type="grid",
                )

        assert result == {"success": False, "error": "Duplicate task (dedup)"}
        mock_run.assert_not_called()

    def test_not_found_error_no_retry(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=True))):
            with patch(
                "apps.trading.engines.execution.run_bot",
                return_value={"success": False, "error": "Bot 123 not found"},
            ):
                with patch.object(run_trading_bot, "retry") as mock_retry:
                    result = _run_task(
                        run_trading_bot,
                        bot_id="11111111-1111-1111-1111-111111111111",
                        bot_type="grid",
                    )

        assert result == {"success": False, "error": "Bot 123 not found"}
        mock_retry.assert_not_called()

    def test_retryable_error_raises_retry(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=True))):
            with patch(
                "apps.trading.engines.execution.run_bot",
                return_value={"success": False, "error": "Rate limited"},
            ):
                with patch.object(run_trading_bot, "retry", side_effect=Retry()) as mock_retry:
                    with pytest.raises(Retry):
                        _run_task(
                            run_trading_bot,
                            bot_id="11111111-1111-1111-1111-111111111111",
                            bot_type="grid",
                        )

        mock_retry.assert_called()
        exc = mock_retry.call_args_list[0].kwargs["exc"]
        assert str(exc) == "Rate limited"

    def test_exception_in_run_bot_retries(self):
        from apps.trading.tasks import run_trading_bot

        with patch("django.core.cache.cache", MagicMock(add=MagicMock(return_value=True))):
            with patch("apps.trading.engines.execution.run_bot", side_effect=RuntimeError("boom")):
                with patch.object(run_trading_bot, "retry", side_effect=Retry()) as mock_retry:
                    with pytest.raises(Retry):
                        _run_task(
                            run_trading_bot,
                            bot_id="11111111-1111-1111-1111-111111111111",
                            bot_type="grid",
                        )

        mock_retry.assert_called()


# ---------------------------------------------------------------------------
# start_bot / stop_bot
# ---------------------------------------------------------------------------


class TestStartBot:
    def test_start_grid_bot(self, user):
        bot = _grid_bot(user)
        assert bot.is_running is False

        result = trade_tasks.start_bot(str(bot.id), bot_type="grid")

        assert result == {"success": True, "status": "started"}
        bot.refresh_from_db()
        assert bot.is_running is True
        assert bot.started_at is not None

    def test_start_martingale_bot(self, user, martingale_bot_subscription):
        bot = _martingale_bot(user, martingale_bot_subscription)

        result = trade_tasks.start_bot(str(bot.id), bot_type="martingale")

        assert result == {"success": True, "status": "started"}
        bot.refresh_from_db()
        assert bot.is_running is True

    def test_start_quantum_bot(self, quantum_fund):
        bot = _quantum_bot(quantum_fund)

        result = trade_tasks.start_bot(str(bot.id), bot_type="quantum_ai")

        assert result == {"success": True, "status": "started"}
        bot.refresh_from_db()
        assert bot.is_running is True

    def test_start_missing_bot(self, user):
        result = trade_tasks.start_bot("11111111-1111-1111-1111-111111111111", bot_type="grid")

        assert result == {
            "success": False,
            "error": "Bot not found: 11111111-1111-1111-1111-111111111111",
        }


class TestStopBot:
    def test_stop_grid_bot(self, user):
        bot = _grid_bot(user, is_running=True)

        result = trade_tasks.stop_bot(str(bot.id), bot_type="grid")

        assert result == {"success": True, "status": "stopped"}
        bot.refresh_from_db()
        assert bot.is_running is False
        assert bot.stopped_at is not None

    def test_stop_martingale_bot(self, user, martingale_bot_subscription):
        bot = _martingale_bot(user, martingale_bot_subscription, is_running=True)

        result = trade_tasks.stop_bot(str(bot.id), bot_type="martingale")

        assert result == {"success": True, "status": "stopped"}
        bot.refresh_from_db()
        assert bot.is_running is False

    def test_stop_missing_not_found(self, user):
        result = trade_tasks.stop_bot("11111111-1111-1111-1111-111111111111", bot_type="grid")

        assert result == {
            "success": False,
            "error": "Bot not found: 11111111-1111-1111-1111-111111111111",
        }


# ---------------------------------------------------------------------------
# check_all_active_bots
# ---------------------------------------------------------------------------


class TestCheckAllActiveBots:
    def test_dispatches_running_bots(self, user, martingale_bot_subscription, quantum_fund):
        grid = _grid_bot(user, is_running=True)
        martingale = _martingale_bot(user, martingale_bot_subscription, is_running=True)
        quantum = _quantum_bot(quantum_fund, is_running=True)
        # Non-running bots must not be dispatched
        _grid_bot(user, bot_name="Stopped Grid")

        with patch.object(trade_tasks.run_trading_bot, "delay") as mock_delay:
            result = trade_tasks.check_all_active_bots()

        assert result["count"] == 3
        assert result["scheduled_bots"] == [str(grid.id) for grid in [grid, martingale, quantum]]

        calls = [c.args for c in mock_delay.call_args_list]
        assert (str(grid.id),) in calls
        assert (str(martingale.id),) in calls
        assert (str(quantum.id),) in calls

    def test_dispatch_kwargs_bot_type(self, user, martingale_bot_subscription, quantum_fund):
        _grid_bot(user, is_running=True)
        _martingale_bot(user, martingale_bot_subscription, is_running=True)
        _quantum_bot(quantum_fund, is_running=True)

        with patch("apps.trading.tasks.run_trading_bot.delay") as mock_delay:
            trade_tasks.check_all_active_bots()

        kwcalls = [c.kwargs for c in mock_delay.call_args_list]
        assert {"bot_type": "grid"} in kwcalls
        assert {"bot_type": "martingale"} in kwcalls
        assert {"bot_type": "quantum_ai"} in kwcalls

    def test_skips_deleted_and_not_running(self, user):
        _grid_bot(user, is_running=False)
        running = _grid_bot(user, is_running=True)
        deleted = _grid_bot(user, is_running=True)
        deleted.is_deleted = True
        deleted.save()

        with patch.object(trade_tasks.run_trading_bot, "delay") as mock_delay:
            result = trade_tasks.check_all_active_bots()

        assert result["count"] == 1
        assert result["scheduled_bots"] == [str(running.id)]
        assert mock_delay.call_count == 1


# ---------------------------------------------------------------------------
# check_stale_bots / _handle_stale_bot
# ---------------------------------------------------------------------------


class TestHandleStaleBot:
    def test_restore_mode_when_open_position(self, user):
        """Stale bot with open position → restart in restore_mode."""
        bot = _grid_bot(user, is_running=True)
        bot.exchange_name = "binance"
        bot.trading_pair = "BTC/USDT"
        bot.save()

        mock_adapter = MagicMock()
        mock_adapter.fetch_position.return_value = {"contracts": 5}

        with patch("apps.trading.exchanges.get_adapter", return_value=mock_adapter):
            with patch("apps.exchanges.models.ExchangeCredentials.objects.get") as mock_creds:
                mock_creds.return_value.get_decrypted_credentials.return_value = {}
                mock_creds.return_value.is_testnet = True
                with patch("apps.trading.tasks.run_trading_bot.delay") as mock_delay:
                    with patch(
                        "core.telegram_service.TelegramService.send_admin_alert"
                    ) as mock_alert:
                        trade_tasks._handle_stale_bot(bot, "grid")

        bot.refresh_from_db()
        assert bot.is_running is False
        mock_delay.assert_called_once_with(str(bot.id), "grid", restore_mode=True)
        mock_alert.assert_called_once()

    def test_mark_stopped_when_no_position(self, user):
        bot = _grid_bot(user, is_running=True)
        bot.exchange_name = "binance"
        bot.save()

        mock_adapter = MagicMock()
        mock_adapter.fetch_position.return_value = {"contracts": 0}

        with patch("apps.trading.exchanges.get_adapter", return_value=mock_adapter):
            with patch("apps.exchanges.models.ExchangeCredentials.objects.get") as mock_creds:
                mock_creds.return_value.get_decrypted_credentials.return_value = {}
                mock_creds.return_value.is_testnet = True
                with patch("apps.trading.tasks.run_trading_bot.delay") as mock_delay:
                    with patch(
                        "core.telegram_service.TelegramService.send_admin_alert"
                    ) as mock_alert:
                        trade_tasks._handle_stale_bot(bot, "grid")

        bot.refresh_from_db()
        assert bot.is_running is False
        mock_delay.assert_not_called()
        mock_alert.assert_not_called()

    def test_position_check_error_marks_stopped(self, user):
        bot = _grid_bot(user, is_running=True)
        bot.exchange_name = "binance"

        mock_adapter = MagicMock()
        mock_adapter.fetch_position.side_effect = Exception("exchange down")

        with patch("apps.trading.exchanges.get_adapter", return_value=mock_adapter):
            with patch("apps.exchanges.models.ExchangeCredentials.objects.get") as mock_creds:
                mock_creds.return_value.get_decrypted_credentials.return_value = {}
                mock_creds.return_value.is_testnet = True
                with patch("apps.trading.tasks.run_trading_bot.delay") as mock_delay:
                    trade_tasks._handle_stale_bot(bot, "grid")

        bot.refresh_from_db()
        assert bot.is_running is False
        mock_delay.assert_not_called()


class TestCheckStaleBots:
    def test_restores_and_stops(self, user):
        import datetime

        from django.utils import timezone

        cutoff = timezone.now() - datetime.timedelta(minutes=6)

        with_position = _grid_bot(user, is_running=True)
        with_position.last_heartbeat = cutoff
        with_position.save()

        no_position = _grid_bot(user, is_running=True)
        no_position.last_heartbeat = cutoff
        no_position.save()

        def fake_handle(bot, bot_type):
            if bot.id == with_position.id:
                q = bot
                q.recovery_mode = "restore"
            else:
                q = bot
                q.recovery_mode = "stop"
            q.save()

        with patch("apps.trading.tasks._handle_stale_bot", side_effect=fake_handle) as mock_handle:
            result = trade_tasks.check_stale_bots()

        assert mock_handle.call_count == 2
        assert result["restored"] == 2
        assert result["errors"] == 0

    def test_never_heartbeat_included(self, user):
        from datetime import timedelta

        from django.utils import timezone

        old_start = timezone.now() - timedelta(minutes=10)

        bot = _grid_bot(user, is_running=True)
        bot.last_heartbeat = None
        bot.started_at = old_start
        bot.save()

        with patch("apps.trading.tasks._handle_stale_bot") as mock_handle:
            result = trade_tasks.check_stale_bots()

        assert mock_handle.call_count == 1
        assert result["restored"] == 1


# ---------------------------------------------------------------------------
# heartbeat_check / reset_monthly_signal_limits
# ---------------------------------------------------------------------------


class TestHeartbeatCheck:
    def test_delegates_to_check_stale_bots(self):
        with patch(
            "apps.trading.tasks.check_stale_bots",
            return_value={"restored": 2, "stopped": 1, "errors": 0},
        ) as mock_stale:
            result = trade_tasks.heartbeat_check()

        mock_stale.assert_called_once()
        assert result == {"restored": 2, "stopped": 1, "errors": 0}


class TestResetMonthlySignalLimits:
    def test_resets_used_bots_only(self, user):
        used = _signal_bot(user, bot_name="Used", signals_used_this_month=7)
        unused = _signal_bot(user, bot_name="Clean", signals_used_this_month=0)

        result = trade_tasks.reset_monthly_signal_limits()

        assert result == {"reset_count": 1}
        used.refresh_from_db()
        unused.refresh_from_db()
        assert used.signals_used_this_month == 0
        assert unused.signals_used_this_month == 0

    def test_returns_zero_when_nothing_to_reset(self, user):
        _signal_bot(user=user, bot_name="Clean", signals_used_this_month=0)
        assert trade_tasks.reset_monthly_signal_limits() == {"reset_count": 0}


# ---------------------------------------------------------------------------
# accrue_quantum_ai_profits / distribute_quantum_ai_profits
# ---------------------------------------------------------------------------


class TestAccrueQuantumAIProfits:
    def test_runs_service_for_active_funds(self, quantum_fund):
        with patch(
            "services.quantum_ai_fund.QuantumAIFundService.update_fund_performance",
            return_value=None,
        ) as mock_update:
            result = trade_tasks.accrue_quantum_ai_profits()

        mock_update.assert_called_once_with(str(quantum_fund.id), quantum_fund.total_fund_value)
        assert result == [{"fund": "Master Fund", "success": True}]

    def test_catches_service_error_per_fund(self, quantum_fund):
        with patch(
            "services.quantum_ai_fund.QuantumAIFundService.update_fund_performance",
            side_effect=Exception("oops"),
        ):
            result = trade_tasks.accrue_quantum_ai_profits()

        assert result == [{"fund": "Master Fund", "success": False, "error": "oops"}]

    def test_skips_inactive_funds(self, quantum_fund):
        quantum_fund.is_active = False
        quantum_fund.save()

        with patch(
            "services.quantum_ai_fund.QuantumAIFundService.update_fund_performance",
        ) as mock_update:
            result = trade_tasks.accrue_quantum_ai_profits()

        mock_update.assert_not_called()
        assert result == []


class TestDistributeQuantumAIProfits:
    def test_distributes_proportionally(self, user, second_user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment

        # Rebuild fund with clean profit so smoothing math is deterministic
        quantum_fund.total_fund_value = Decimal("100000")
        quantum_fund.total_profit = Decimal("1000")
        quantum_fund.total_deposits = Decimal("10000")
        quantum_fund.save()

        inv_a = QuantumAIInvestment.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("6000"),
            share_percentage=Decimal("60"),
            status="active",
        )
        inv_b = QuantumAIInvestment.objects.create(
            user=second_user,
            fund=quantum_fund,
            amount=Decimal("4000"),
            share_percentage=Decimal("40"),
            status="active",
        )

        result = trade_tasks.distribute_quantum_ai_profits()

        assert result == {"distributed_to": 2}
        inv_a.refresh_from_db()
        inv_b.refresh_from_db()
        assert inv_a.accrued_profit == Decimal("600")
        assert inv_b.accrued_profit == Decimal("400")

    def test_no_distribution_when_no_profit(self, user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment

        quantum_fund.total_profit = Decimal("0")
        quantum_fund.save()
        QuantumAIInvestment.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("1000"),
            share_percentage=Decimal("100"),
            status="active",
        )

        result = trade_tasks.distribute_quantum_ai_profits()

        assert result == {"distributed_to": 0}

    def test_credits_reserve_on_excess(self, user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment

        # 20% actual return > 15% max → 5% excess goes to reserve
        quantum_fund.total_profit = Decimal("2000")
        quantum_fund.total_deposits = Decimal("10000")
        quantum_fund.save()
        QuantumAIInvestment.objects.create(
            user=user,
            fund=quantum_fund,
            amount=Decimal("10000"),
            share_percentage=Decimal("100"),
            status="active",
        )

        result = trade_tasks.distribute_quantum_ai_profits()

        assert result == {"distributed_to": 1}
        reserve = quantum_fund.reserve
        assert reserve.balance == Decimal("500")
