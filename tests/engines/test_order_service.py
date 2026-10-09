"""Behavior tests for BotOrderService (apps/trading/engines/order_service.py).

Covers the stateless order execution + persistence layer: create_order
branching across Amount_Type and order_type, close_position side/reduce-only
logic and percentage math, cancel_all_orders error tolerance, save_order DB
persistence (user, indicators, details wrapping, Telegram notification), and
the qty helper for dollar vs coin amount types.
"""

from unittest import mock

import pytest

from apps.trading.engines.order_service import BotOrderService


@pytest.fixture
def no_order_sync():
    """Disconnect the BotOrder -> investments.Order post_save sync signal.

    save_order's own persistence path is what's under test; the sync signal
    requires a non-null user and would otherwise break no-user BotOrders.
    """
    from django.db.models.signals import post_save

    from apps.bots import signals as bots_signals
    from apps.bots.models import BotOrder

    post_save.disconnect(bots_signals.sync_bot_order_to_investments, sender=BotOrder)
    yield
    post_save.connect(bots_signals.sync_bot_order_to_investments, sender=BotOrder)


def _make_service(adapter=None, pair_config=None, bot_config=None, symbol="BTC/USDT"):
    return BotOrderService(
        adapter=adapter or mock.MagicMock(),
        symbol=symbol,
        pair_config=pair_config or {},
        bot_config=bot_config or {},
    )


class TestCreateOrder:
    def test_dollar_type_market_uses_cost(self):
        service = _make_service(pair_config={"Amount_Type": "dollar"})
        service.adapter.create_market_order_with_cost.return_value = {"id": "c1"}
        result = service.create_order("market", "buy", 100.0, None)
        service.adapter.create_market_order_with_cost.assert_called_once_with(
            "BTC/USDT", "buy", 100.0
        )
        assert result == {"id": "c1"}

    def test_dollar_type_limit_uses_limit(self):
        service = _make_service(pair_config={"Amount_Type": "dollar"})
        service.adapter.create_limit_order.return_value = {"id": "l1"}
        result = service.create_order("limit", "buy", 100.0, 50000.0)
        service.adapter.create_limit_order.assert_called_once_with(
            "BTC/USDT", "buy", 100.0, 50000.0
        )
        assert result == {"id": "l1"}

    def test_dollar_type_unknown_order_type_falls_back_to_cost(self):
        service = _make_service(pair_config={"Amount_Type": "dollar"})
        service.create_order("weird", "sell", 50.0, None)
        service.adapter.create_market_order_with_cost.assert_called_once_with(
            "BTC/USDT", "sell", 50.0
        )
        service.adapter.create_market_order.assert_not_called()

    def test_coin_type_market_uses_plain(self):
        service = _make_service(pair_config={"Amount_Type": "coin"})
        service.adapter.create_market_order.return_value = {"id": "m1"}
        result = service.create_order("market", "buy", 0.002, None)
        service.adapter.create_market_order.assert_called_once_with("BTC/USDT", "buy", 0.002)
        assert result == {"id": "m1"}

    def test_coin_type_limit_uses_limit(self):
        service = _make_service(pair_config={"Amount_Type": "coin"})
        service.create_order("limit", "sell", 0.002, 49000.0)
        service.adapter.create_limit_order.assert_called_once_with(
            "BTC/USDT", "sell", 0.002, 49000.0
        )

    def test_coin_type_unknown_order_type_falls_back_to_plain(self):
        service = _make_service(pair_config={"Amount_Type": "coin"})
        service.create_order("weird", "buy", 0.002, None)
        service.adapter.create_market_order.assert_called_once_with("BTC/USDT", "buy", 0.002)
        service.adapter.create_market_order_with_cost.assert_not_called()

    def test_missing_amount_type_uses_plain(self):
        service = _make_service(pair_config={})
        service.create_order("market", "buy", 0.002, None)
        service.adapter.create_market_order.assert_called_once_with("BTC/USDT", "buy", 0.002)

    def test_exception_returns_none(self):
        service = _make_service(pair_config={"Amount_Type": "coin"})
        service.adapter.create_market_order.side_effect = Exception("API error")
        assert service.create_order("market", "buy", 0.002, None) is None


class TestClosePosition:
    def test_no_position_returns_none(self):
        service = _make_service()
        service.adapter.fetch_position.return_value = None
        assert service.close_position("BTC/USDT") is None
        service.adapter.create_market_order.assert_not_called()

    def test_zero_contracts_returns_none(self):
        service = _make_service()
        service.adapter.fetch_position.return_value = {"contracts": 0}
        assert service.close_position("BTC/USDT") is None

    def test_short_closes_with_buy_reduce_only(self):
        service = _make_service()
        service.adapter.fetch_position.return_value = {
            "contracts": 0.002,
            "unrealized_pnl": 10.0,
            "side": "short",
        }
        service.adapter.create_market_order.return_value = {"id": "close1"}
        result = service.close_position("BTC/USDT")
        service.adapter.create_market_order.assert_called_once_with(
            "BTC/USDT", "buy", 0.002, {"reduceOnly": True}
        )
        assert result["detail"] == {"id": "close1"}
        assert result["pnl"] == 10.0
        assert result["side"] == "short"
        assert result["percentage"] == 0.0

    def test_long_closes_with_sell_reduce_only(self):
        service = _make_service()
        service.adapter.fetch_position.return_value = {
            "contracts": 0.005,
            "unrealized_pnl": -5.0,
            "side": "long",
        }
        service.adapter.create_market_order.return_value = {"id": "close2"}
        result = service.close_position("BTC/USDT")
        service.adapter.create_market_order.assert_called_once_with(
            "BTC/USDT", "sell", 0.005, {"reduceOnly": True}
        )
        assert result["pnl"] == -5.0
        assert result["side"] == "long"

    def test_percentage_mode_calculates_percentage(self):
        service = _make_service(pair_config={"SLTP_Type": "percentage"})
        service.adapter.fetch_position.return_value = {
            "contracts": 0.01,
            "unrealized_pnl": 2.0,
            "side": "long",
        }
        service.adapter.create_market_order.return_value = {"id": "close3"}
        result = service.close_position("BTC/USDT")
        assert result["percentage"] == 2.0 / 0.01 * 1000

    def test_unknown_side_returns_none(self):
        service = _make_service()
        service.adapter.fetch_position.return_value = {"contracts": 0.01, "side": "flat"}
        assert service.close_position("BTC/USDT") is None
        service.adapter.create_market_order.assert_not_called()

    def test_exception_returns_none(self):
        service = _make_service()
        service.adapter.fetch_position.side_effect = Exception("boom")
        assert service.close_position("BTC/USDT") is None


class TestCancelAllOrders:
    def test_calls_adapter(self):
        service = _make_service()
        service.cancel_all_orders("BTC/USDT")
        service.adapter.cancel_all_orders.assert_called_once_with("BTC/USDT")

    def test_exception_is_tolerated(self):
        service = _make_service()
        service.adapter.cancel_all_orders.side_effect = Exception("timeout")
        service.cancel_all_orders("BTC/USDT")  # must not raise


class TestSaveOrder:
    def test_creates_order_without_user(self, db, no_order_sync):
        service = _make_service(
            pair_config={"quantity": 0.002},
            bot_config={"bot_name": "grid", "current_price": 50000.0, "exchange_name": "Bybit"},
        )
        order = service.save_order("Buy", "entry", {"ref": "a"})
        assert order is not None
        assert order.Pair == "BTC/USDT"
        assert order.Side == "Buy"
        assert order.Order_type == "Market"
        assert order.Quantity == 0.002
        assert order.Price == 50000.0
        assert order.Details == {"ref": "a"}
        assert order.user is None

    def test_wraps_non_dict_details(self, db, no_order_sync):
        service = _make_service(bot_config={"bot_name": "grid"})
        order = service.save_order("Sell", "exit", "raw-string")
        assert order.Details == {"raw": "raw-string"}

    def test_creates_order_with_user_and_indicators(self, db, user):
        service = _make_service(
            pair_config={"quantity": 0.001},
            bot_config={"user_id": user.id, "bot_name": "grid", "current_price": 49000.0},
        )
        order = service.save_order(
            "Buy",
            "entry",
            {"x": 1},
            indicators={
                "EMA": 1.5,
                "RSI": 40.0,
                "PrevRSI": 35.0,
                "RSI_color": "white",
                "RSI_prev_color": "white",
                "BB": "upper",
                "TSI": 2.0,
                "ADX": 25.0,
            },
        )
        assert order.user_id == user.id
        assert order.Indicators is not None
        assert order.Indicators.EMA == 1.5
        assert order.Indicators.RSI == 40.0
        assert order.Indicators.Prev_RSI == 35.0
        assert order.Indicators.Color == "white"
        assert order.Indicators.ADX == 25.0

    def test_no_indicators_skips_indicator_creation(self, db, user):
        service = _make_service(bot_config={"user_id": user.id, "bot_name": "grid"})
        order = service.save_order("Buy", "entry")
        assert order.Indicators is None

    def test_missing_user_id_returns_none(self, db):
        service = _make_service(bot_config={"user_id": 999999})
        assert service.save_order("Buy", "entry") is None

    def test_telegram_notification_sent_when_configured(self, db, user):
        from django.contrib.auth import get_user_model

        real = get_user_model().objects.get(id=user.id)
        real.telegram_token = "tok"
        real.telegram_chat_id = "12345"
        service = _make_service(
            pair_config={"quantity": 0.002},
            bot_config={
                "user_id": user.id,
                "bot_name": "grid",
                "current_price": 51000.0,
                "exchange_name": "Bybit",
            },
        )
        with (
            mock.patch("core.telegram_service.TelegramService.send_trade_alert") as send,
            mock.patch.object(get_user_model().objects, "get", return_value=real),
        ):
            order = service.save_order("Buy", "entry", {"x": 1})
            send.assert_called_once()
            trade_data = send.call_args[0][1]
            assert trade_data["symbol"] == "BTC/USDT"
            assert trade_data["side"] == "Buy"
            assert trade_data["amount"] == "0.002"
            assert trade_data["price"] == "51000.0"
        assert order is not None

    def test_telegram_error_does_not_fail_order(self, db, user):
        from django.contrib.auth import get_user_model

        real = get_user_model().objects.get(id=user.id)
        real.telegram_token = "tok"
        real.telegram_chat_id = "12345"
        service = _make_service(bot_config={"user_id": user.id, "bot_name": "grid"})
        with (
            mock.patch(
                "core.telegram_service.TelegramService.send_trade_alert",
                side_effect=Exception("tg down"),
            ),
            mock.patch.object(get_user_model().objects, "get", return_value=real),
        ):
            order = service.save_order("Buy", "entry")
        assert order is not None


class TestQty:
    def test_dollar_type_calculates_coin_quantities(self):
        service = _make_service(
            pair_config={
                "Amount_Type": "dollar",
                "quantity": 100.0,
                "favor_level_qty": 50.0,
                "against_level_qty": 25.0,
            }
        )
        qty, favor, against = service.qty(50000.0)
        assert qty == round(100.0 / 50000.0, 4)
        assert favor == round(50.0 / 50000.0, 4)
        assert against == round(25.0 / 50000.0, 4)

    def test_coin_type_passes_raw_quantities(self):
        service = _make_service(
            pair_config={
                "Amount_Type": "coin",
                "quantity": 0.002,
                "favor_level_qty": 0.001,
                "against_level_qty": 0.0005,
            }
        )
        qty, favor, against = service.qty(50000.0)
        assert qty == 0.002
        assert favor == 0.001
        assert against == 0.0005


class TestTradeIntegrity:
    """Phase 1 (persistence): BotOrder trade-record integrity (migration 0017).

    Locks the four guarantees a restart depends on: real fill price, bot
    linkage, open/closed status and entry reason + realized P/L.
    """

    # ---- price resolution (pure units, no DB) -----------------------------

    def test_extract_fill_price_reads_exchange_fields(self):
        from apps.trading.engines.order_service import _extract_fill_price

        assert _extract_fill_price({"average": "49900.5"}) == 49900.5
        assert _extract_fill_price({"price": 50000}) == 50000.0
        assert _extract_fill_price({"fillPrice": 1.25}) == 1.25
        # unified fill price (average) is more authoritative than order price
        assert _extract_fill_price({"price": 10, "average": 20}) == 20.0

    def test_extract_fill_price_rejects_zero_garbage_non_dict(self):
        from apps.trading.engines.order_service import _extract_fill_price

        assert _extract_fill_price({"price": 0}) is None
        assert _extract_fill_price({"price": "abc"}) is None
        assert _extract_fill_price({"price": None}) is None
        assert _extract_fill_price({"ref": "a"}) is None
        assert _extract_fill_price("raw-string") is None
        assert _extract_fill_price(None) is None

    def test_resolve_price_precedence_explicit_then_exchange_then_config(self):
        from apps.trading.engines.order_service import _resolve_price

        config = {"current_price": 50000.0}
        # explicit argument wins
        assert _resolve_price(100.0, {"average": 90.0}, config) == 100.0
        # exchange fill beats the config fallback
        assert _resolve_price(None, {"average": 90.0}, config) == 90.0
        # config fallback kept for legacy callers
        assert _resolve_price(None, None, config) == 50000.0
        # nothing known -> 0 (never a crash, never a false fill)
        assert _resolve_price(None, None, {}) == 0.0
        assert _resolve_price("junk", {"price": "junk"}, {}) == 0.0

    # ---- persistence: price ----------------------------------------------

    def test_exchange_fill_price_beats_config_fallback(self, db, no_order_sync):
        service = _make_service(
            pair_config={"quantity": 0.002},
            bot_config={"bot_name": "grid", "current_price": 50000.0},
        )
        order = service.save_order("Buy", "entry", {"average": 49900.5, "ref": "x"})
        assert float(order.Price) == 49900.5

    def test_config_price_used_when_exchange_silent(self, db, no_order_sync):
        service = _make_service(
            bot_config={"bot_name": "grid", "current_price": 50000.0},
        )
        order = service.save_order("Buy", "entry", {"ref": "a"})
        assert order.Price == 50000.0

    def test_price_is_zero_when_nothing_known(self, db, no_order_sync):
        service = _make_service(bot_config={"bot_name": "grid"})
        order = service.save_order("Buy", "entry")
        assert float(order.Price) == 0.0

    # ---- persistence: defaults -------------------------------------------

    def test_defaults_are_closed_unlinked_no_reason_no_pnl(self, db, no_order_sync):
        service = _make_service(bot_config={"bot_name": "grid"})
        order = service.save_order("Buy", "entry")
        assert order.Status == "closed"
        assert order.Reason is None
        assert order.Realized_PnL is None
        assert order.bot_type is None
        assert order.bot_id is None
        assert order.grid_bot_id is None
        assert order.signal_bot_id is None
        assert order.martingale_bot_id is None

    def test_entry_persists_open_status_and_reason(self, db, no_order_sync):
        service = _make_service(pair_config={"quantity": 0.002}, bot_config={"bot_name": "grid"})
        order = service.save_order(
            "Buy", "entry", None, reason="EMA + RSI BUY LONG (CASE1)", status="open"
        )
        assert order.Status == "open"
        assert order.Reason == "EMA + RSI BUY LONG (CASE1)"
        assert order.Realized_PnL is None

    def test_exit_persists_closed_status_and_realized_pnl(self, db, no_order_sync):
        service = _make_service(bot_config={"bot_name": "grid"})
        order = service.save_order("Sell", "exit", None, status="closed", pnl=12.5)
        assert order.Status == "closed"
        assert float(order.Realized_PnL) == 12.5

    # ---- persistence: bot linkage ----------------------------------------

    def test_bot_id_and_bot_type_persisted_from_config(self, db, no_order_sync):
        service = _make_service(
            bot_config={"bot_name": "grid", "bot_type": "grid", "bot_id": "4242"}
        )
        order = service.save_order("Buy", "entry")
        assert order.bot_type == "grid"
        assert order.bot_id == "4242"
        # unresolvable id -> linkage skipped, order still written
        assert order.grid_bot_id is None

    def test_resolvable_grid_bot_fk_is_wired(self, db, user, no_order_sync):
        from decimal import Decimal

        from apps.bots.models import GridBot

        bot = GridBot.objects.create(
            user=user,
            bot_name="Grid 1",
            exchange_name="binance",
            trading_pair="ETH/USDT",
            base_amount=Decimal("100"),
            favor_levels=3,
            against_levels=3,
        )
        service = _make_service(
            bot_config={
                "bot_name": "Grid 1",
                "bot_type": "grid",
                "bot_id": str(bot.id),
            }
        )
        order = service.save_order("Buy", "entry")
        assert order.grid_bot_id == bot.id
        assert order.bot_id == str(bot.id)
        assert order.bot_type == "grid"

    def test_quantum_ai_gets_no_polymorphic_fk(self, db, no_order_sync):
        """quantum_ai_investment points at InvestorPortfolio, not QuantumAIBot."""
        service = _make_service(
            bot_config={"bot_name": "QBot", "bot_type": "quantum_ai", "bot_id": "77"}
        )
        order = service.save_order("Buy", "entry")
        assert order.bot_type == "quantum_ai"
        assert order.bot_id == "77"
        assert order.quantum_ai_investment_id is None
        assert order.grid_bot_id is None

    def test_broken_linkage_never_loses_the_order(self, db, no_order_sync):
        """A bad FK resolution must fall back to bot_id/bot_type, not 500."""
        service = _make_service(
            bot_config={"bot_name": "grid", "bot_type": "grid", "bot_id": "not-an-id"}
        )
        order = service.save_order("Buy", "entry")
        assert order is not None
        assert order.bot_id == "not-an-id"
        assert order.grid_bot_id is None
