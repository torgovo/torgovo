import pytest

from apps.trading.strategies.quantum_ai import QuantumAIStrategy


class TestQuantumAIInitialization:
    def test_init_defaults(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        assert strategy.name == "Quantum AI"
        assert strategy.parameters["symbol"] == "BTC/USDT"
        assert strategy.parameters["quantity"] == 10
        assert strategy.parameters["Amount_Type"] == "dollar"
        assert strategy.parameters["RSI_Lower"] == 30
        assert strategy.parameters["RSI_Upper"] == 70
        assert strategy.parameters["favor_levels"] == 5
        assert strategy.parameters["against_levels"] == 5
        assert strategy.parameters["Stop_Loss"] == -2
        assert strategy.parameters["Take_Profit"] == 5
        assert strategy.current_side == "None"
        assert strategy.count == 0

    def test_init_custom_parameters(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "ETH/USDT",
                "quantity": 0.1,
                "Amount_Type": "coin",
                "RSI_Lower": 25,
                "RSI_Upper": 75,
                "favor_levels": 3,
                "against_levels": 3,
            }
        )
        assert strategy.parameters["symbol"] == "ETH/USDT"
        assert strategy.parameters["quantity"] == 0.1
        assert strategy.parameters["Amount_Type"] == "coin"
        assert strategy.parameters["RSI_Lower"] == 25

    def test_init_missing_symbol(self):
        with pytest.raises(ValueError, match="Missing required parameters"):
            QuantumAIStrategy({})

    def test_init_indicator_defaults(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        assert strategy.EMA == 0.0
        assert strategy.RSI == 50.0
        assert strategy.PrevRSI == 50.0
        assert strategy.RSI_color is None
        assert strategy.BB is None

    def test_required_parameters(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        assert "symbol" in strategy.required_parameters


class TestQuantumAIUpdateIndicators:
    def test_update_indicators(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.update_indicators(
            {
                "EMA": 49500.0,
                "RSI": 35.0,
                "PrevRSI": 45.0,
                "RSI_color": "white",
                "RSI_prev_color": "green",
                "BB": "Crossing Down Band",
            }
        )
        assert strategy.EMA == 49500.0
        assert strategy.RSI == 35.0
        assert strategy.PrevRSI == 45.0
        assert strategy.RSI_color == "white"
        assert strategy.BB == "Crossing Down Band"

    def test_update_indicators_partial(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.update_indicators({"EMA": 50000.0})
        assert strategy.EMA == 50000.0
        assert strategy.RSI == 50.0

    def test_update_indicators_empty(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.EMA = 100.0
        strategy.update_indicators({})
        assert strategy.EMA == 0.0


class TestQuantumAIEvaluateConditions:
    def test_ema_conditions(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.EMA = 50000.0
        conditions = strategy._evaluate_conditions(51000.0)
        assert conditions["EMA_Buy"] is True
        assert conditions["EMA_Sell"] is False

        conditions = strategy._evaluate_conditions(49000.0)
        assert conditions["EMA_Buy"] is False
        assert conditions["EMA_Sell"] is True

    def test_ema_zero_does_not_trigger(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.EMA = 0.0
        conditions = strategy._evaluate_conditions(51000.0)
        assert conditions["EMA_Buy"] is False
        assert conditions["EMA_Sell"] is False

    def test_rsi_buy_conditions(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.PrevRSI = 25.0
        strategy.RSI_color = "white"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["RSI_Buy"] is True
        assert conditions["RSI_Sell"] is False

    def test_rsi_sell_conditions(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.PrevRSI = 75.0
        strategy.RSI_color = "white"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["RSI_Sell"] is True
        assert conditions["RSI_Buy"] is False

    def test_rsi_not_white_does_not_trigger(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.PrevRSI = 25.0
        strategy.RSI_color = "red"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["RSI_Buy"] is False

    def test_bb_buy_conditions(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.BB = "Crossing Down Band"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["BB_Buy"] is True
        assert conditions["BB_Sell"] is False

    def test_bb_sell_conditions(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.BB = "Crossing Up Band"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["BB_Sell"] is True
        assert conditions["BB_Buy"] is False

    @pytest.mark.parametrize(
        "bb_signal,expect_buy,expect_sell",
        [
            ("Crossing Down Band", True, False),
            ("Closed Below Lower Band", True, False),
            ("Up Arrow", True, False),
            ("Crossing Up Band", False, True),
            ("Closed Above Upper Band", False, True),
            ("Down Arrow", False, True),
            ("Middle Band", False, False),
            (None, False, False),
        ],
    )
    def test_bb_various_signals(self, bb_signal, expect_buy, expect_sell):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.BB = bb_signal
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["BB_Buy"] == expect_buy
        assert conditions["BB_Sell"] == expect_sell

    def test_trade_state_no_trade(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.count = 0
        strategy.current_side = "None"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["NoTrade"] is True
        assert conditions["BuyTrade"] is False
        assert conditions["SellTrade"] is False

    def test_trade_state_buy_trade(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.count = 1
        strategy.current_side = "Buy"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["NoTrade"] is False
        assert conditions["BuyTrade"] is True
        assert conditions["SellTrade"] is False

    def test_trade_state_sell_trade(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.count = 1
        strategy.current_side = "Sell"
        conditions = strategy._evaluate_conditions(50000.0)
        assert conditions["NoTrade"] is False
        assert conditions["BuyTrade"] is False
        assert conditions["SellTrade"] is True


class TestQuantumAIEntryCases:
    def make_market_data(
        self,
        price=50000.0,
        ema=49000.0,
        rsi=25,
        prev_rsi=25,
        rsi_color="white",
        bb="Crossing Down Band",
    ):
        return {
            "ticker": {"last": price},
            "indicators": {
                "EMA": ema,
                "RSI": rsi,
                "PrevRSI": prev_rsi,
                "RSI_color": rsi_color,
                "BB": bb,
            },
        }

    def test_case1_ema_plus_rsi_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_RSI_Entry": "both",
            }
        )
        md = self.make_market_data(
            price=51000.0, ema=50000.0, rsi=35, prev_rsi=25, rsi_color="white"
        )
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"
        assert "CASE1" in signal.reason
        assert signal.metadata["entry_case"] == "EMA + RSI BUY LONG (CASE1)"

    def test_case1_ema_plus_rsi_sell(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_RSI_Entry": "both",
            }
        )
        md = self.make_market_data(
            price=49000.0,
            ema=50000.0,
            rsi=75,
            prev_rsi=75,
            rsi_color="white",
            bb="Crossing Up Band",
        )
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "sell"
        assert "CASE1" in signal.reason

    def test_case2_ema_plus_bb_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_BB_Entry": "buy",
            }
        )
        md = self.make_market_data(
            price=51000.0, ema=50000.0, rsi=50, prev_rsi=50, rsi_color="white"
        )
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"
        assert "CASE2" in signal.reason

    def test_case3_bb_plus_rsi_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_RSI_Entry": "none",
                "BB_RSI_Entry": "both",
            }
        )
        md = self.make_market_data(price=50000.0, rsi=35, prev_rsi=25, rsi_color="white")
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"
        assert "CASE3" in signal.reason

    def test_case4_rsi_only_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "RSI_Entry": "both",
            }
        )
        md = self.make_market_data(price=50000.0, rsi=35, prev_rsi=25, rsi_color="white")
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"

    def test_case5_bb_only_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_Entry": "buy",
            }
        )
        md = self.make_market_data(price=50000.0)
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"

    def test_case6_all_three_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_BB_RSI_Entry": "both",
            }
        )
        md = self.make_market_data(
            price=51000.0, ema=50000.0, rsi=35, prev_rsi=25, rsi_color="white"
        )
        signal = strategy.execute(md, {})
        assert signal is not None
        assert signal.action == "buy"

    def test_entry_disabled_returns_none(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_RSI_Entry": "none",
                "EMA_BB_Entry": "none",
                "BB_RSI_Entry": "none",
                "RSI_Entry": "none",
                "BB_Entry": "none",
                "EMA_BB_RSI_Entry": "none",
            }
        )
        md = self.make_market_data(
            price=51000.0, ema=50000.0, rsi=35, prev_rsi=25, rsi_color="white"
        )
        signal = strategy.execute(md, {})
        assert signal is None

    def test_no_price_data_returns_none(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        signal = strategy.execute({"ticker": {}}, {})
        assert signal is None

    def test_entry_sets_state(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT", "EMA_RSI_Entry": "both"})
        md = self.make_market_data(
            price=51000.0, ema=50000.0, rsi=35, prev_rsi=25, rsi_color="white"
        )
        signal = strategy.execute(md, {})
        assert signal is not None
        assert strategy.current_side == "Buy"
        assert strategy.count == 1
        assert strategy.signals_generated == 1


class TestQuantumAIExitConditions:
    def make_market_data(
        self, price=50000.0, ema=None, rsi=50, prev_rsi=50, rsi_color="white", bb=None
    ):
        indicators = {"RSI": rsi, "PrevRSI": prev_rsi, "RSI_color": rsi_color}
        if bb is not None:
            indicators["BB"] = bb
        if ema is not None:
            indicators["EMA"] = ema
        else:
            indicators["EMA"] = 0
        return {"ticker": {"last": price}, "indicators": indicators}

    def make_position(self, side="long", entry_price=50000.0, contracts=0.01, unrealized_pnl=0):
        return {
            "side": side,
            "entry_price": entry_price,
            "contracts": contracts,
            "unrealized_pnl": unrealized_pnl,
        }

    def test_bb_exit_buy_trade(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=51000.0, bb="Crossing Up Band")
        signal = strategy.execute(md, {}, self.make_position("long"))
        assert signal is not None
        assert signal.action == "sell"
        assert "TP" in signal.reason
        assert "CASE1" in signal.reason

    def test_rsi_exit_buy_trade(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "RSI_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=51000.0, rsi=75, prev_rsi=75, rsi_color="white")
        signal = strategy.execute(md, {}, self.make_position("long"))
        assert signal is not None
        assert signal.action == "sell"
        assert "CASE2" in signal.reason

    def test_bb_rsi_exit_buy_trade(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_RSI_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(
            price=51000.0, rsi=75, prev_rsi=75, rsi_color="white", bb="Crossing Up Band"
        )
        signal = strategy.execute(md, {}, self.make_position("long"))
        assert signal is not None
        assert signal.action == "sell"

    def test_sell_exit_rsi(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "RSI_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Sell"
        md = self.make_market_data(price=49000.0, rsi=25, prev_rsi=25, rsi_color="white")
        signal = strategy.execute(md, {}, self.make_position("short"))
        assert signal is not None
        assert signal.action == "buy"

    def test_sell_exit_bb(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Sell"
        md = self.make_market_data(price=49000.0, bb="Crossing Down Band")
        signal = strategy.execute(md, {}, self.make_position("short"))
        assert signal is not None
        assert signal.action == "buy"

    def test_exit_resets_state(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=51000.0, bb="Crossing Up Band")
        signal = strategy.execute(md, {}, self.make_position("long"))
        assert signal is not None
        assert strategy.current_side == "None"
        assert strategy.count == 0

    def test_sltp_percentage_stop_loss(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "Stop_Loss": -5,
                "Take_Profit": 10,
                "SLTP_Type": "percentage",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        entry_price = 100.0
        current_price = 93.0
        contracts = 1.0
        unrealized_pnl = (current_price - entry_price) * contracts
        md = self.make_market_data(price=current_price)
        pos = self.make_position(
            "long", entry_price=entry_price, contracts=contracts, unrealized_pnl=unrealized_pnl
        )
        signal = strategy.execute(md, {}, pos)
        assert signal is not None
        assert "STOP LOSS" in signal.reason

    def test_sltp_percentage_take_profit(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "Stop_Loss": -5,
                "Take_Profit": 10,
                "SLTP_Type": "percentage",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        entry_price = 100.0
        current_price = 112.0
        contracts = 1.0
        unrealized_pnl = (current_price - entry_price) * contracts
        md = self.make_market_data(price=current_price)
        pos = self.make_position(
            "long", entry_price=entry_price, contracts=contracts, unrealized_pnl=unrealized_pnl
        )
        signal = strategy.execute(md, {}, pos)
        assert signal is not None
        assert "TAKE PROFIT" in signal.reason

    def test_sltp_dollars_stop_loss(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "Stop_Loss": -50,
                "Take_Profit": 100,
                "SLTP_Type": "dollars",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=100.0)
        pos = self.make_position("long", contracts=1.0, unrealized_pnl=-60.0)
        signal = strategy.execute(md, {}, pos)
        assert signal is not None
        assert "STOP LOSS" in signal.reason

    def test_sltp_dollars_take_profit(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "Stop_Loss": -50,
                "Take_Profit": 100,
                "SLTP_Type": "dollars",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=100.0)
        pos = self.make_position("long", contracts=1.0, unrealized_pnl=120.0)
        signal = strategy.execute(md, {}, pos)
        assert signal is not None
        assert "TAKE PROFIT" in signal.reason

    def test_no_exit_when_not_hit(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "BB_Exit": "tp",
            }
        )
        strategy.count = 1
        strategy.current_side = "Buy"
        md = self.make_market_data(price=50100.0)
        signal = strategy.execute(md, {}, self.make_position("long"))
        assert signal is None


class TestQuantumAIGridCalculations:
    def test_calculate_grids_buy(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "favor_levels": 3,
                "against_levels": 3,
                "favor_level_difference": 0.5,
                "against_level_difference": 0.5,
            }
        )
        favor, against = strategy.calculate_grids("buy", 50000.0)
        assert len(favor) == 3
        assert len(against) == 3
        assert all(p > 50000.0 for p in favor)
        assert all(p < 50000.0 for p in against)

    def test_calculate_grids_sell(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "favor_levels": 3,
                "against_levels": 3,
                "favor_level_difference": 0.5,
                "against_level_difference": 0.5,
            }
        )
        favor, against = strategy.calculate_grids("sell", 50000.0)
        assert len(favor) == 3
        assert len(against) == 3
        assert all(p < 50000.0 for p in favor)
        assert all(p > 50000.0 for p in against)

    def test_calculate_grids_buy_level_prices(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "favor_levels": 2,
                "against_levels": 2,
                "favor_level_difference": 1.0,
                "against_level_difference": 1.0,
            }
        )
        favor, against = strategy.calculate_grids("buy", 100.0)
        assert favor == pytest.approx([101.0, 102.0], rel=1e-4)
        assert against == pytest.approx([99.0, 98.0], rel=1e-4)

    def test_calculate_grids_sell_level_prices(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "favor_levels": 2,
                "against_levels": 2,
                "favor_level_difference": 1.0,
                "against_level_difference": 1.0,
            }
        )
        favor, against = strategy.calculate_grids("sell", 100.0)
        assert favor == pytest.approx([99.0, 98.0], rel=1e-4)
        assert against == pytest.approx([101.0, 102.0], rel=1e-4)

    def test_calculate_grids_rounding(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "favor_levels": 1,
                "against_levels": 1,
                "favor_level_difference": 0.5,
                "against_level_difference": 0.5,
            }
        )
        favor, against = strategy.calculate_grids("buy", 50000.0)
        assert favor[0] == round(50000 * 1.005, 6)

    def test_grid_levels_in_entry_signal_metadata(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "EMA_RSI_Entry": "both",
                "favor_levels": 2,
                "against_levels": 2,
            }
        )
        md = {
            "ticker": {"last": 51000.0},
            "indicators": {
                "EMA": 50000.0,
                "RSI": 35,
                "PrevRSI": 25,
                "RSI_color": "white",
                "BB": None,
            },
        }
        signal = strategy.execute(md, {})
        assert signal is not None
        assert len(signal.metadata["favor_levels"]) == 2
        assert len(signal.metadata["against_levels"]) == 2


class TestQuantumAIPortfolioManagement:
    def test_sync_position_long(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        pos = {"side": "long", "contracts": 0.01, "entry_price": 50000.0}
        strategy._sync_position_state(pos)
        assert strategy.current_side == "Buy"
        assert strategy.count == 1

    def test_sync_position_short(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        pos = {"side": "short", "contracts": 0.01, "entry_price": 50000.0}
        strategy._sync_position_state(pos)
        assert strategy.current_side == "Sell"
        assert strategy.count == 1

    def test_sync_position_no_position(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy._sync_position_state({"side": "long", "contracts": 0, "entry_price": 0})
        assert strategy.current_side == "None"
        assert strategy.count == 0

    def test_sync_position_none(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy._sync_position_state(None)
        assert strategy.current_side == "None"
        assert strategy.count == 0

    def test_prepare_order_data_dollar_type(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "quantity": 100,
                "Amount_Type": "dollar",
                "Order_Type": "market",
                "favor_levels": 3,
                "against_levels": 3,
                "favor_level_qty": 50,
                "against_level_qty": 50,
                "favor_level_difference": 0.5,
                "against_level_difference": 0.5,
            }
        )
        data = strategy.prepare_order_data("Buy", 50000.0)
        assert data["category"] == "futures"
        assert data["symbol"] == "BTC/USDT"
        assert data["side"] == "Buy"
        assert data["qty"] == round(100 / 50000.0, 4)
        assert data["favor_level_qty"] == round(50 / 50000.0, 4)

    def test_prepare_order_data_coin_type(self):
        strategy = QuantumAIStrategy(
            {
                "symbol": "BTC/USDT",
                "quantity": 0.01,
                "Amount_Type": "coin",
                "favor_level_qty": 0.005,
            }
        )
        data = strategy.prepare_order_data("Buy", 50000.0)
        assert data["qty"] == 0.01
        assert data["favor_level_qty"] == 0.005
        assert data["qty_dollar"] is None

    def test_reset_state(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.current_side = "Buy"
        strategy.count = 1
        strategy.favor_levels = [100.0, 101.0]
        strategy.against_levels = [99.0, 98.0]
        strategy.Percentage = 5.0
        strategy.Unrealized_Pnl = 10.0
        strategy.reset_state()
        assert strategy.current_side == "None"
        assert strategy.count == 0
        assert strategy.favor_levels == []
        assert strategy.against_levels == []
        assert strategy.Percentage == 0.0
        assert strategy.Unrealized_Pnl == 0.0


class TestQuantumAIStatus:
    def test_get_status(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        status = strategy.get_status()
        assert status["name"] == "Quantum AI"
        assert status["current_side"] == "None"
        assert status["count"] == 0
        assert status["favor_levels"] == []
        assert status["against_levels"] == []
        assert "indicators" in status

    def test_get_status_with_trade(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.current_side = "Buy"
        strategy.count = 1
        strategy.current_price = 51000.0
        strategy.favor_levels = [51500.0]
        status = strategy.get_status()
        assert status["current_side"] == "Buy"
        assert status["count"] == 1
        assert status["current_price"] == 51000.0

    def test_get_indicator_data(self):
        strategy = QuantumAIStrategy({"symbol": "BTC/USDT"})
        strategy.update_indicators(
            {
                "EMA": 50000.0,
                "RSI": 45.0,
                "PrevRSI": 50.0,
                "RSI_color": "white",
                "BB": "Middle Band",
            }
        )
        s = strategy.get_indicator_data()
        assert "BTC/USDT" in s
        assert "50000.0" in s
        assert "45.0" in s
        assert "Middle Band" in s
