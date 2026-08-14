"""Behavior tests for apps/bots models.

Complements the existing smoke/status tests in tests/bots/test_views.py by
exercising the model logic that powers the API: SignalBot id/message/credential
generation and signal accounting, soft-delete semantics, grid/martingale
one-bot-per-subscription constraints, GridBot.save_state, ReserveFund
target/cover/audit behavior, and QuantumAIFund/QuantumAIInvestment return
smoothing.
"""

import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError

pytestmark = pytest.mark.django_db


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


class TestSignalBotGeneration:
    def test_bot_id_generated_on_save(self, user):
        bot = _signal_bot(user)
        parts = bot.bot_id.split("-")
        assert len(parts) == 3
        assert all(len(p) == 5 for p in parts)
        assert all(int(p, 16) >= 0 for p in parts)

    def test_bot_id_unique_across_bots(self, user):
        b1 = _signal_bot(user, bot_name="One")
        b2 = _signal_bot(user, bot_name="Two")
        assert b1.bot_id != b2.bot_id

    def test_existing_bot_id_preserved(self, user):
        bot = _signal_bot(user)
        bot_id = bot.bot_id
        bot.bot_name = "Renamed"
        bot.save()
        assert bot.bot_id == bot_id

    def test_webhook_url_generated(self, user):
        bot = _signal_bot(user)
        assert bot.webhook_url == "http://localhost:8000/api/webhooks/custombot/"

    def test_secret_key_generated(self, user):
        bot = _signal_bot(user)
        assert bot.secret_key
        assert len(bot.secret_key) >= 32

    def test_webhook_message_template_links_bot(self, user):
        bot = _signal_bot(user)
        msg = bot.webhook_message
        assert msg["bot_id"] == bot.bot_id
        assert msg["secret"] == bot.secret_key
        assert msg["exchange"] == "binance"

    def test_webhook_message_uses_tradingview_placeholders(self, user):
        bot = _signal_bot(user)
        msg = bot.webhook_message
        assert msg["Pair"] == "{{syminfo.basecurrency}}/{{syminfo.currency}}"
        assert msg["position_size"] == "{{strategy.position_size}}"
        assert msg["side"] == "{{strategy.order.action}}"
        assert msg["timestamp"] == "{{timenow}}"
        assert msg["order_id"] == "{{strategy.order.id}}"

    def test_generate_webhook_credentials_fills_missing(self, user):
        bot = _signal_bot(user)
        bot.webhook_url = ""
        bot.secret_key = ""
        bot.generate_webhook_credentials()
        assert bot.webhook_url.startswith("http://localhost:8000/api/webhooks/custom/")
        assert bot.webhook_url.endswith(f"{bot.id}/")
        assert bot.secret_key
        assert len(bot.secret_key) >= 32

    def test_generate_webhook_credentials_keeps_existing(self, user):
        bot = _signal_bot(user)
        original_url = bot.webhook_url
        original_secret = bot.secret_key
        bot.generate_webhook_credentials()
        assert bot.webhook_url == original_url
        assert bot.secret_key == original_secret


class TestSignalBotAccounting:
    def test_increment_signal_count(self, user):
        bot = _signal_bot(user)
        bot.signals_used_this_month = 5
        bot.save(update_fields=["signals_used_this_month"])

        bot.increment_signal_count()
        bot.refresh_from_db()

        assert bot.signals_used_this_month == 6
        assert bot.last_triggered is not None

    def test_signals_remaining(self, user):
        bot = _signal_bot(user)
        bot.signal_limit = 10
        bot.signals_used_this_month = 4
        assert bot.signals_remaining == 6

    def test_signals_remaining_clamped_at_zero(self, user):
        bot = _signal_bot(user)
        bot.signal_limit = 10
        bot.signals_used_this_month = 15
        assert bot.signals_remaining == 0

    def test_success_rate_zero_when_no_trades(self, user):
        bot = _signal_bot(user)
        assert bot.success_rate == 0

    def test_success_rate_percentage(self, user):
        bot = _signal_bot(user)
        bot.total_trades = 4
        bot.successful_trades = 3
        assert bot.success_rate == 75.0

    def test_success_rate_rounded(self, user):
        bot = _signal_bot(user)
        bot.total_trades = 3
        bot.successful_trades = 1
        assert bot.success_rate == 33.33


class TestSoftDeleteSemantics:
    def test_delete_flags_row_keeps_record(self, user):
        bot = _signal_bot(user)
        bot.delete()
        bot.refresh_from_db()
        assert bot.is_deleted is True
        assert bot.deleted_at is not None

    def test_restore_clears_flags(self, user):
        bot = _signal_bot(user)
        bot.delete()
        bot.restore()
        bot.refresh_from_db()
        assert bot.is_deleted is False
        assert bot.deleted_at is None

    def test_hard_delete_removes_row(self, user):
        bot = _signal_bot(user)
        bot_id = bot.id
        bot.hard_delete()
        from apps.bots.models import SignalBot

        assert not SignalBot.objects.filter(id=bot_id).exists()


class TestGridBot:
    def test_save_state_updates_both_fields(self, user):
        bot = _grid_bot(user)
        bot.save_state(active_orders=["a", "b"], grid_levels={"buy": [1, 2], "sell": [3, 4]})
        bot.refresh_from_db()
        assert bot.active_orders == ["a", "b"]
        assert bot.current_grid_levels == {"buy": [1, 2], "sell": [3, 4]}

    def test_save_state_partial_update(self, user):
        bot = _grid_bot(user)
        bot.active_orders = ["old"]
        bot.save(update_fields=["active_orders"])

        bot.save_state(active_orders=["new"])
        bot.refresh_from_db()

        assert bot.active_orders == ["new"]
        assert bot.current_grid_levels == {}

    def test_one_grid_bot_per_subscription(self, user, bot_subscription):
        _grid_bot(user, subscription=bot_subscription)
        with pytest.raises(IntegrityError):
            _grid_bot(user, subscription=bot_subscription)


class TestMartingaleBot:
    def test_one_martingale_bot_per_subscription(self, user, martingale_bot_subscription):
        from apps.bots.models import MartingaleBot

        MartingaleBot.objects.create(
            user=user,
            subscription=martingale_bot_subscription,
            bot_name="M",
            exchange_name="binance",
            trading_pair="BTC/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
        )
        with pytest.raises(IntegrityError):
            MartingaleBot.objects.create(
                user=user,
                subscription=martingale_bot_subscription,
                bot_name="M2",
                exchange_name="binance",
                trading_pair="BTC/USDT",
                base_amount=Decimal("100"),
                favor_levels=3,
                against_levels=3,
            )


class TestReserveFund:
    def _reserve(self, deposits=Decimal("1000"), buffer_pct=Decimal("10"), balance=Decimal("100")):
        from apps.bots.models import QuantumAIFund, ReserveFund

        fund = QuantumAIFund.objects.create(
            name=f"Fund-{uuid.uuid4().hex[:6]}",
            master_api_key="key",
            master_secret_key="secret",
            total_deposits=deposits,
            monthly_min_return=Decimal("2.00"),
            monthly_max_return=Decimal("15.00"),
            reserve_buffer_pct=buffer_pct,
        )
        return ReserveFund.objects.create(fund=fund, balance=balance)

    def test_is_below_target_zero_deposits(self):
        reserve = self._reserve(deposits=Decimal("0"), balance=Decimal("100"))
        assert reserve.is_below_target() is True

    def test_is_below_target_when_under(self):
        reserve = self._reserve(
            deposits=Decimal("1000"), buffer_pct=Decimal("10"), balance=Decimal("50")
        )
        assert reserve.is_below_target() is True

    def test_is_below_target_when_met(self):
        reserve = self._reserve(
            deposits=Decimal("1000"), buffer_pct=Decimal("10"), balance=Decimal("100")
        )
        assert reserve.is_below_target() is False

    def test_can_cover_within_balance(self):
        reserve = self._reserve(balance=Decimal("100"))
        assert reserve.can_cover(Decimal("100")) is True

    def test_cannot_cover_beyond_balance(self):
        reserve = self._reserve(balance=Decimal("100"))
        assert reserve.can_cover(Decimal("100.01")) is False

    def test_record_transaction_writes_audit_row(self):
        from apps.bots.models import ReserveTransaction

        reserve = self._reserve(balance=Decimal("100"))
        reserve.record_transaction(
            Decimal("1000"), Decimal("-100"), "shortfall_cover", "cover payout"
        )
        txn = ReserveTransaction.objects.get(reserve=reserve)
        assert txn.fund == reserve.fund
        assert txn.amount == Decimal("-100")
        assert txn.balance_before == Decimal("1000")
        assert txn.balance_after == Decimal("900")
        assert txn.transaction_type == "shortfall_cover"
        assert txn.description == "cover payout"


class TestQuantumFundSmoothing:
    def test_smoothed_return_floors_at_min(self, quantum_fund):
        assert quantum_fund.calculate_smoothed_return(Decimal("1")) == Decimal("2.00")

    def test_smoothed_return_passes_through(self, quantum_fund):
        assert quantum_fund.calculate_smoothed_return(Decimal("10")) == Decimal("10")

    def test_smoothed_return_caps_at_max(self, quantum_fund):
        assert quantum_fund.calculate_smoothed_return(Decimal("20")) == Decimal("15.00")

    def test_excess_return_positive_when_over_max(self, quantum_fund):
        assert quantum_fund.calculate_excess_return(Decimal("20")) == Decimal("5")

    def test_excess_return_negative_when_under_min(self, quantum_fund):
        assert quantum_fund.calculate_excess_return(Decimal("1")) == Decimal("-1")


class TestQuantumAIInvestment:
    def _investment(self, user, fund, amount, status="active"):
        from apps.bots.models import QuantumAIInvestment

        return QuantumAIInvestment.objects.create(
            user=user, fund=fund, amount=amount, status=status
        )

    def test_share_percentage_zero_when_no_deposits(self, user, quantum_fund_without_deposits):
        inv = self._investment(user, quantum_fund_without_deposits, Decimal("100"))
        assert inv.calculate_share_percentage() == Decimal("0")

    def test_share_percentage_of_total(self, user, quantum_fund):
        inv = self._investment(user, quantum_fund, Decimal("5000"))
        assert inv.calculate_share_percentage() == Decimal("10.0")

    def test_profit_share_zero_when_inactive(self, user, quantum_fund):
        inv = self._investment(user, quantum_fund, Decimal("5000"), status="pending")
        assert inv.calculate_profit_share(Decimal("10")) == Decimal("0")

    def test_profit_share_zero_when_no_deposits(self, user, quantum_fund_without_deposits):
        inv = self._investment(user, quantum_fund_without_deposits, Decimal("100"))
        assert inv.calculate_profit_share(Decimal("10")) == Decimal("0")

    def test_profit_share_active(self, user, quantum_fund):
        # 5000 of 50000 deposits = 10% share; smoothed 10% -> 500 USDT
        inv = self._investment(user, quantum_fund, Decimal("5000"))
        assert inv.calculate_profit_share(Decimal("10")) == Decimal("500")

    def test_profit_share_capped_at_max(self, user, quantum_fund):
        # actual 20% smoothed to 15% -> 50000 * 0.15 * 0.10 = 750 USDT
        inv = self._investment(user, quantum_fund, Decimal("5000"))
        assert inv.calculate_profit_share(Decimal("20")) == Decimal("750")

    def test_profit_share_floored_at_min(self, user, quantum_fund):
        # actual 1% smoothed to 2% -> 50000 * 0.02 * 0.10 = 100 USDT
        inv = self._investment(user, quantum_fund, Decimal("5000"))
        assert inv.calculate_profit_share(Decimal("1")) == Decimal("100")
