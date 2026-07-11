import pytest
from apps.trading.strategies.webhook_alerts import WebhookAlertStrategy
from apps.trading.strategies.base import Signal


class TestWebhookAlertInitialization:
    def test_init_defaults(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT'})
        assert strategy.name == 'Webhook Alert'
        assert strategy.parameters['symbol'] == 'BTC/USDT'
        assert strategy.parameters['default_amount'] == 0.01
        assert strategy.parameters['use_percentage'] is False
        assert strategy.parameters['percentage'] == 10
        assert strategy.parameters['require_secret'] is True
        assert strategy.parameters['stop_loss_percentage'] == 2
        assert strategy.parameters['take_profit_percentage'] == 5

    def test_init_custom(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'ETH/USDT',
            'default_amount': 0.5,
            'use_percentage': True,
            'percentage': 25,
            'require_secret': False,
            'secret': 'mysecret',
        })
        assert strategy.parameters['default_amount'] == 0.5
        assert strategy.parameters['use_percentage'] is True
        assert strategy.parameters['percentage'] == 25
        assert strategy.parameters['require_secret'] is False
        assert strategy.parameters['secret'] == 'mysecret'

    def test_init_missing_symbol(self):
        with pytest.raises(ValueError, match='Missing required parameters'):
            WebhookAlertStrategy({})

    def test_required_parameters(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT'})
        assert 'symbol' in strategy.required_parameters


class TestWebhookPayloadValidation:
    def test_validate_webhook_valid(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
            'require_secret': True,
        })
        result = strategy.validate_webhook({
            'action': 'buy',
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
        })
        assert result['valid'] is True
        assert result['errors'] == []

    def test_validate_webhook_invalid_secret(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
        })
        result = strategy.validate_webhook({
            'action': 'buy',
            'secret': 'wrongsecret',
        })
        assert result['valid'] is False
        assert 'Invalid or missing secret' in result['errors']

    def test_validate_webhook_missing_secret(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
        })
        result = strategy.validate_webhook({'action': 'buy'})
        assert result['valid'] is False
        assert 'Invalid or missing secret' in result['errors']

    def test_validate_webhook_no_secret_required(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'require_secret': False,
        })
        result = strategy.validate_webhook({'action': 'buy'})
        assert result['valid'] is True

    def test_validate_webhook_invalid_action(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'invalid_action'})
        assert result['valid'] is False
        assert any('Invalid action' in e for e in result['errors'])

    def test_validate_webhook_empty_action(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': ''})
        assert result['valid'] is False

    def test_validate_webhook_invalid_symbol_format(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'buy', 'symbol': 'BTCUSDT'})
        assert result['valid'] is False
        assert any('Invalid symbol format' in e for e in result['errors'])

    def test_validate_webhook_valid_symbol_without_slash(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'buy'})
        assert result['valid'] is True

    def test_validate_webhook_long_action(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'long'})
        assert result['valid'] is True

    def test_validate_webhook_short_action(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'short'})
        assert result['valid'] is True

    def test_validate_webhook_close_action(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT', 'require_secret': False})
        result = strategy.validate_webhook({'action': 'close'})
        assert result['valid'] is True


class TestWebhookPositionSizing:
    def make_strategy(self, **overrides):
        params = {'symbol': 'BTC/USDT', 'require_secret': False, **overrides}
        return WebhookAlertStrategy(params)

    def test_amount_from_webhook_takes_precedence(self):
        strategy = self.make_strategy(default_amount=0.01)
        amount = strategy._calculate_amount(
            {'amount': '0.5'}, {}, {}, 'BTC/USDT'
        )
        assert amount == 0.5

    def test_amount_uses_default(self):
        strategy = self.make_strategy(default_amount=0.05)
        amount = strategy._calculate_amount({}, {}, {}, 'BTC/USDT')
        assert amount == 0.05

    def test_amount_percentage_of_balance(self):
        strategy = self.make_strategy(use_percentage=True, percentage=10)
        account_info = {'balance': {'free': {'USDT': 10000}}}
        market_data = {'ticker': {'last': 50000.0}}
        amount = strategy._calculate_amount({}, market_data, account_info, 'BTC/USDT')
        expected = (10000 * 0.10) / 50000.0
        assert amount == pytest.approx(expected)

    def test_amount_percentage_no_price_falls_back_to_default(self):
        strategy = self.make_strategy(use_percentage=True, percentage=10, default_amount=0.01)
        account_info = {'balance': {'free': {'USDT': 10000}}}
        market_data = {'ticker': {'last': 1}}
        amount = strategy._calculate_amount({}, market_data, account_info, 'BTC/USDT')
        expected = (10000 * 0.10) / 1
        assert amount == pytest.approx(expected)

    def test_amount_percentage_no_balance(self):
        strategy = self.make_strategy(use_percentage=True, default_amount=0.01)
        account_info = {'balance': {'free': {}}}
        amount = strategy._calculate_amount({}, {}, account_info, 'BTC/USDT')
        assert amount == 0.0

    def test_amount_webhook_overrides_percentage(self):
        strategy = self.make_strategy(use_percentage=True, percentage=10, default_amount=0.01)
        amount = strategy._calculate_amount({'amount': '1.0'}, {}, {}, 'BTC/USDT')
        assert amount == 1.0

    def test_amount_symbol_without_slash(self):
        strategy = self.make_strategy(use_percentage=True, percentage=10)
        account_info = {'balance': {'free': {'USDT': 5000}}}
        market_data = {'ticker': {'last': 100.0}}
        amount = strategy._calculate_amount({}, market_data, account_info, 'BTCUSDT')
        expected = (5000 * 0.10) / 100.0
        assert amount == pytest.approx(expected)

    def test_amount_negative_webhook(self):
        strategy = self.make_strategy(default_amount=0.01)
        amount = strategy._calculate_amount({'amount': '-1.0'}, {}, {}, 'BTC/USDT')
        assert amount == -1.0


class TestWebhookSignalProcessing:
    def make_strategy(self, **overrides):
        params = {'symbol': 'BTC/USDT', 'require_secret': False, **overrides}
        return WebhookAlertStrategy(params)

    def test_process_buy_signal(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {'balance': {'free': {'USDT': 1000}}}
        )
        assert signal is not None
        assert signal.action == 'buy'
        assert signal.symbol == 'BTC/USDT'
        assert signal.amount == 0.01
        assert signal.order_type == 'market'

    def test_process_sell_signal(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'sell', 'amount': 0.5},
            {'ticker': {'last': 3000.0}},
            {}
        )
        assert signal is not None
        assert signal.action == 'sell'
        assert signal.amount == 0.5

    def test_process_long_normalized_to_buy(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'long', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {'balance': {'free': {'USDT': 1000}}}
        )
        assert signal.action == 'buy'

    def test_process_short_normalized_to_sell(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'short', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {'balance': {'free': {'USDT': 1000}}}
        )
        assert signal.action == 'sell'

    def test_process_close_signal(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'close', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert signal is not None
        assert signal.action == 'close'

    def test_process_with_custom_symbol(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'symbol': 'ETH/USDT', 'amount': 0.1},
            {'ticker': {'last': 3000.0}},
            {}
        )
        assert signal.symbol == 'ETH/USDT'

    def test_process_with_limit_order(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01, 'type': 'limit', 'price': 49000.0},
            {},
            {}
        )
        assert signal.order_type == 'limit'
        assert signal.price == 49000.0

    def test_process_with_custom_sl_tp(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01, 'stop_loss': 48000.0, 'take_profit': 52000.0},
            {},
            {}
        )
        assert signal.stop_loss == 48000.0
        assert signal.take_profit == 52000.0

    def test_process_calculates_sl_tp_from_defaults(self):
        strategy = self.make_strategy(
            stop_loss_percentage=2,
            take_profit_percentage=5,
        )
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert signal.stop_loss == 49000.0
        assert signal.take_profit == 52500.0

    def test_process_with_comment(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01, 'comment': 'TradingView Alert'},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert 'TradingView Alert' in signal.reason

    def test_process_invalid_action(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'invalid', 'amount': 0.01},
            {},
            {}
        )
        assert signal is None

    def test_process_rejected_secret(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
            'require_secret': True,
        })
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01, 'secret': 'wrong'},
            {},
            {}
        )
        assert signal is None

    def test_process_accepted_secret(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'secret': 'mysecret',
            'require_secret': True,
        })
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01, 'secret': 'mysecret'},
            {'ticker': {'last': 50000.0}},
            {'balance': {'free': {'USDT': 1000}}}
        )
        assert signal is not None

    def test_process_zero_amount_rejected(self):
        strategy = self.make_strategy(default_amount=0)
        signal = strategy.process_webhook(
            {'action': 'buy'},
            {'ticker': {'last': 50000.0}},
            {'balance': {'free': {'USDT': 1000}}}
        )
        assert signal is None

    def test_process_empty_payload(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook({}, {}, {})
        assert signal is None

    def test_signal_metadata_source(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert signal.metadata['source'] == 'webhook'
        assert 'raw_data' in signal.metadata

    def test_execute_with_webhook_signal(self):
        strategy = self.make_strategy()
        market_data = {
            'ticker': {'last': 50000.0},
            'webhook_signal': {'action': 'buy', 'amount': 0.01}
        }
        signal = strategy.execute(market_data, {'balance': {'free': {'USDT': 1000}}})
        assert signal is not None
        assert signal.action == 'buy'

    def test_execute_without_webhook_signal(self):
        strategy = self.make_strategy()
        signal = strategy.execute({'ticker': {'last': 50000.0}}, {})
        assert signal is None

    def test_signals_generated_tracking(self):
        strategy = self.make_strategy()
        assert strategy.signals_generated == 0
        strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert strategy.signals_generated == 1

    def test_last_signal_set(self):
        strategy = self.make_strategy()
        signal = strategy.process_webhook(
            {'action': 'buy', 'amount': 0.01},
            {'ticker': {'last': 50000.0}},
            {}
        )
        assert strategy.last_signal == signal


class TestWebhookAlertStatus:
    def test_get_status(self):
        strategy = WebhookAlertStrategy({'symbol': 'BTC/USDT'})
        status = strategy.get_status()
        assert status['name'] == 'Webhook Alert'
        assert status['require_secret'] is True
        assert status['use_percentage'] is False

    def test_get_status_no_secret(self):
        strategy = WebhookAlertStrategy({
            'symbol': 'BTC/USDT',
            'require_secret': False,
            'use_percentage': True,
        })
        status = strategy.get_status()
        assert status['require_secret'] is False
        assert status['use_percentage'] is True
