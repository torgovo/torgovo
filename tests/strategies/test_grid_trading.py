import pytest

from apps.trading.strategies.grid_trading import GridTradingStrategy


class TestGridTradingInitialization:
    def test_init_defaults(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        assert strategy.name == "Grid Trading"
        assert strategy.parameters["symbol"] == "BTC/USDT"
        assert strategy.parameters["amount_per_grid"] == 10
        assert strategy.parameters["grid_levels"] == 10
        assert strategy.parameters["grid_spacing_percentage"] == 1.0
        assert strategy.grid_orders == {}
        assert strategy.grid_initialized is False

    def test_init_custom_parameters(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "ETH/USDT",
                "amount_per_grid": 20,
                "grid_levels": 5,
                "grid_spacing_percentage": 2.0,
                "upper_limit": 4000,
                "lower_limit": 2000,
            }
        )
        assert strategy.parameters["symbol"] == "ETH/USDT"
        assert strategy.parameters["grid_levels"] == 5
        assert strategy.parameters["grid_spacing_percentage"] == 2.0
        assert strategy.parameters["upper_limit"] == 4000
        assert strategy.parameters["lower_limit"] == 2000

    def test_init_missing_required_params(self):
        with pytest.raises(ValueError, match="Missing required parameters"):
            GridTradingStrategy({})

    def test_init_with_default_amount_per_grid(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT"})
        assert strategy.parameters["amount_per_grid"] == 10

    def test_init_missing_symbol(self):
        with pytest.raises(ValueError, match="Missing required parameters.*symbol"):
            GridTradingStrategy({"amount_per_grid": 10})

    @property
    def required_parameters(self):
        return ["symbol", "amount_per_grid"]


class TestGridTradingCalculateGridLevels:
    def test_calculate_grid_levels_default(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        result = strategy.calculate_grid_levels(100.0)

        assert result["current_price"] == 100.0
        assert result["grid_levels"] == 10
        assert len(result["levels"]) == 11  # grid_levels + 1
        assert result["lower_limit"] < result["current_price"] < result["upper_limit"]

        buy_levels = [lvl for lvl in result["levels"] if lvl["type"] == "buy"]
        sell_levels = [lvl for lvl in result["levels"] if lvl["type"] == "sell"]
        assert len(buy_levels) > 0
        assert len(sell_levels) > 0

    def test_calculate_grid_levels_symmetric_around_price(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_spacing_percentage": 1.0,
                "grid_levels": 10,
            }
        )
        result = strategy.calculate_grid_levels(100.0)
        mid = (result["upper_limit"] + result["lower_limit"]) / 2
        assert mid == pytest.approx(100.0, rel=1e-2)

    def test_calculate_grid_levels_with_explicit_limits(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        result = strategy.calculate_grid_levels(100.0, upper_limit=150.0, lower_limit=50.0)
        assert result["upper_limit"] == 150.0
        assert result["lower_limit"] == 50.0
        assert len(result["levels"]) == 11
        assert result["price_step"] == pytest.approx(10.0)

    def test_calculate_grid_levels_price_step(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 5,
                "grid_spacing_percentage": 2.0,
            }
        )
        result = strategy.calculate_grid_levels(100.0)
        expected_range = 100.0 * (1 + 0.02 * 5 / 2) - 100.0 * (1 - 0.02 * 5 / 2)
        expected_step = expected_range / 5
        assert result["price_step"] == pytest.approx(expected_step)

    def test_calculate_grid_levels_buy_sell_distribution(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 10,
                "grid_spacing_percentage": 1.0,
            }
        )
        result = strategy.calculate_grid_levels(100.0)
        levels_above = [lvl for lvl in result["levels"] if lvl["price"] > 100.0]
        levels_below = [lvl for lvl in result["levels"] if lvl["price"] < 100.0]
        assert all(lvl["type"] == "sell" for lvl in levels_above)
        assert all(lvl["type"] == "buy" for lvl in levels_below)

    def test_calculate_grid_levels_edge_no_buy(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 10,
            }
        )
        result = strategy.calculate_grid_levels(5.0, upper_limit=10.0, lower_limit=0.0)
        buy_levels = [lvl for lvl in result["levels"] if lvl["type"] == "buy"]
        assert len(buy_levels) >= 0


class TestGridTradingPlaceGridOrders:
    def test_execute_initialize_grid_on_first_call(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        market_data = {"ticker": {"last": 50000.0}}
        account_info = {"balance": {"free": {"USDT": 1000}}}

        signal = strategy.execute(market_data, account_info)
        assert signal is not None
        assert signal.action == "buy"
        assert signal.symbol == "BTC/USDT"
        assert signal.order_type == "limit"
        assert strategy.grid_initialized is True

    def test_execute_initialize_grid_correct_amount(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 100})
        market_data = {"ticker": {"last": 50000.0}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        buy_price = signal.price
        expected_amount = 100.0 / buy_price
        assert signal.amount == pytest.approx(expected_amount)

    def test_execute_grid_initialization_sets_grid_prices_in_metadata(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 10,
                "grid_spacing_percentage": 1.0,
            }
        )
        market_data = {"ticker": {"last": 50000}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        assert "grid_prices" in signal.metadata
        assert "upper_limit" in signal.metadata
        assert "lower_limit" in signal.metadata
        assert len(signal.metadata["grid_prices"]) == 11

    def test_execute_second_call_no_signal(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        strategy.grid_initialized = True
        market_data = {"ticker": {"last": 50000.0}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        assert signal is None

    def test_execute_no_price_data(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        market_data = {"ticker": {}}
        signal = strategy.execute(market_data, {})
        assert signal is None

    def test_execute_no_ticker(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        signal = strategy.execute({}, {})
        assert signal is None

    def test_initialize_grid_finds_closest_buy_level(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 4,
                "grid_spacing_percentage": 2.0,
            }
        )
        market_data = {"ticker": {"last": 100.0}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        assert signal.action == "buy"
        assert signal.price < 100.0

    def test_initialize_grid_buy_price_correctness(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_levels": 4,
                "grid_spacing_percentage": 2.0,
            }
        )
        market_data = {"ticker": {"last": 100.0}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        grid_prices = signal.metadata["grid_prices"]
        buy_prices = [p for p in grid_prices if p < 100.0]
        closest_buy = max(buy_prices)
        assert signal.price == closest_buy


class TestGridTradingRiskManagement:
    def test_grid_with_high_amount_uses_base_strategy_sl_tp(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "stop_loss_percentage": 3,
                "take_profit_percentage": 8,
            }
        )
        sl = strategy.calculate_stop_loss(50000, "long")
        assert sl == pytest.approx(48500.0)
        tp = strategy.calculate_take_profit(50000, "long")
        assert tp == pytest.approx(54000.0)


class TestGridTradingStatus:
    def test_get_status_before_init(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        status = strategy.get_status()
        assert status["name"] == "Grid Trading"
        assert status["grid_initialized"] is False
        assert status["active_orders"] == 0

    def test_get_status_after_init(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        strategy.grid_initialized = True
        strategy.grid_orders = {"order1": {}}
        status = strategy.get_status()
        assert status["grid_initialized"] is True
        assert status["active_orders"] == 1

    def test_get_status_inherits_base_fields(self):
        strategy = GridTradingStrategy({"symbol": "BTC/USDT", "amount_per_grid": 10})
        status = strategy.get_status()
        assert "name" in status
        assert "is_running" in status
        assert "signals_generated" in status
        assert "signals_executed" in status
        assert "parameters" in status


class TestGridTradingVariousMarkets:
    def test_low_price_asset(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "SHIB/USDT",
                "amount_per_grid": 100,
                "grid_spacing_percentage": 5.0,
                "grid_levels": 5,
            }
        )
        market_data = {"ticker": {"last": 0.00001}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 1000}}})
        assert signal is not None
        assert signal.price < 0.00001

    def test_high_price_asset(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_spacing_percentage": 0.5,
                "grid_levels": 20,
            }
        )
        market_data = {"ticker": {"last": 100000.0}}
        signal = strategy.execute(market_data, {"balance": {"free": {"USDT": 10000}}})
        assert signal is not None
        assert signal.price < 100000.0
        assert len(signal.metadata["grid_prices"]) == 21

    def test_volatile_market_spacing(self):
        strategy = GridTradingStrategy(
            {
                "symbol": "BTC/USDT",
                "amount_per_grid": 10,
                "grid_spacing_percentage": 3.0,
                "grid_levels": 5,
            }
        )
        grid_info = strategy.calculate_grid_levels(50000.0)
        range_size = grid_info["upper_limit"] - grid_info["lower_limit"]
        expected_range = 50000 * 0.03 * 5
        assert range_size == pytest.approx(expected_range, rel=0.01)
