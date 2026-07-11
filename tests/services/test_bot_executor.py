from unittest.mock import patch, MagicMock

import pytest

from services.bot_executor import BotExecutorService


pytestmark = pytest.mark.django_db


class TestStartGridBot:
    def test_start_success(self):
        mock_bot = MagicMock()
        mock_bot.id = 'bot-123'
        mock_bot.bot_name = 'Test Grid'
        mock_bot.subscription.status = 'active'

        with patch('services.bot_executor.GridBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.run_trading_bot') as mock_task:
                result = BotExecutorService.start_grid_bot('user1', 'bot-123')

                mock_task.delay.assert_called_once_with('bot-123', bot_type='grid')
                assert mock_bot.is_running is True
                assert mock_bot.started_at is not None
                mock_bot.save.assert_called_once_with(
                    update_fields=['is_running', 'started_at', 'updated_at']
                )
                assert result is True

    def test_start_no_subscription(self):
        mock_bot = MagicMock()
        mock_bot.subscription = None

        with patch('services.bot_executor.GridBot.objects.get', return_value=mock_bot):
            with pytest.raises(ValueError, match='No active subscription'):
                BotExecutorService.start_grid_bot('user1', 'bot-123')

    def test_start_inactive_subscription(self):
        mock_bot = MagicMock()
        mock_bot.subscription.status = 'expired'

        with patch('services.bot_executor.GridBot.objects.get', return_value=mock_bot):
            with pytest.raises(ValueError, match='No active subscription'):
                BotExecutorService.start_grid_bot('user1', 'bot-123')

    def test_start_bot_not_found(self):
        with patch('services.bot_executor.GridBot.objects.get', side_effect=Exception('Not found')):
            with pytest.raises(Exception, match='Not found'):
                BotExecutorService.start_grid_bot('user1', 'nonexistent')

    def test_start_creates_celery_task(self):
        mock_bot = MagicMock()
        mock_bot.subscription.status = 'active'

        with patch('services.bot_executor.GridBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.run_trading_bot') as mock_task:
                BotExecutorService.start_grid_bot('user1', 'bot-123')
                mock_task.delay.assert_called_once()


class TestStopGridBot:
    def test_stop_success(self):
        mock_bot = MagicMock()
        mock_bot.id = 'bot-123'

        with patch('services.bot_executor.GridBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.stop_bot') as mock_task:
                result = BotExecutorService.stop_grid_bot('user1', 'bot-123')

                mock_task.delay.assert_called_once_with('bot-123', bot_type='grid')
                assert mock_bot.is_running is False
                assert mock_bot.stopped_at is not None
                mock_bot.save.assert_called_once_with(
                    update_fields=['is_running', 'stopped_at', 'updated_at']
                )
                assert result is True

    def test_stop_bot_not_found(self):
        with patch('services.bot_executor.GridBot.objects.get', side_effect=Exception('Not found')):
            with pytest.raises(Exception):
                BotExecutorService.stop_grid_bot('user1', 'nonexistent')

    def test_stop_checks_user_ownership(self):
        with patch('services.bot_executor.GridBot.objects.get') as mock_get:
            mock_get.side_effect = Exception('Matching query does not exist')
            with pytest.raises(Exception):
                BotExecutorService.stop_grid_bot('other_user', 'bot-123')
            mock_get.assert_called_once_with(id='bot-123', user='other_user')


class TestStartMartingaleBot:
    def test_start_success(self):
        mock_bot = MagicMock()
        mock_bot.id = 'bot-456'
        mock_bot.bot_name = 'Test Martingale'
        mock_bot.subscription.status = 'active'

        with patch('services.bot_executor.MartingaleBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.run_trading_bot') as mock_task:
                result = BotExecutorService.start_martingale_bot('user1', 'bot-456')

                mock_task.delay.assert_called_once_with('bot-456', bot_type='martingale')
                assert mock_bot.is_running is True
                assert result is True

    def test_start_no_subscription(self):
        mock_bot = MagicMock()
        mock_bot.subscription = None

        with patch('services.bot_executor.MartingaleBot.objects.get', return_value=mock_bot):
            with pytest.raises(ValueError, match='No active subscription'):
                BotExecutorService.start_martingale_bot('user1', 'bot-456')

    def test_start_inactive_subscription(self):
        mock_bot = MagicMock()
        mock_bot.subscription.status = 'cancelled'

        with patch('services.bot_executor.MartingaleBot.objects.get', return_value=mock_bot):
            with pytest.raises(ValueError, match='No active subscription'):
                BotExecutorService.start_martingale_bot('user1', 'bot-456')


class TestStopMartingaleBot:
    def test_stop_success(self):
        mock_bot = MagicMock()
        mock_bot.id = 'bot-456'

        with patch('services.bot_executor.MartingaleBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.stop_bot') as mock_task:
                result = BotExecutorService.stop_martingale_bot('user1', 'bot-456')

                mock_task.delay.assert_called_once_with('bot-456', bot_type='martingale')
                assert mock_bot.is_running is False
                assert result is True


class TestExecuteSignalBotOrder:
    def test_execute_success(self):
        mock_bot = MagicMock()
        mock_bot.id = 'bot-789'
        mock_bot.is_active = True
        mock_bot.exchange_name = 'bybit'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.default_amount = Decimal('0.01')

        mock_creds = MagicMock()
        mock_creds.get_decrypted_credentials.return_value = {
            'api_key': 'key123',
            'secret_key': 'secret456',
        }

        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {
            'id': 'order-111',
            'price': 50000.0,
            'amount': 0.01,
        }

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.ExchangeCredentials.objects.get', return_value=mock_creds):
                with patch('services.bot_executor.ccxt') as mock_ccxt:
                    mock_exchange_class = MagicMock(return_value=mock_exchange)
                    mock_ccxt.bybit = mock_exchange_class

                    with patch('services.bot_executor.Indicator.objects.create') as mock_ind:
                        mock_indicator = MagicMock()
                        mock_ind.return_value = mock_indicator
                        with patch('services.bot_executor.Order.objects.create') as mock_order:
                            result = BotExecutorService.execute_signal_bot_order(
                                'user1', 'bot-789',
                                {'side': 'buy', 'Pair': 'BTC/USDT', 'position_size': '0.02'}
                            )

                            mock_exchange.load_markets.assert_called_once()
                            mock_exchange.create_order.assert_called_once_with(
                                symbol='BTC/USDT', type='market', side='buy', amount=0.02
                            )
                            assert mock_bot.total_trades == 1
                            assert mock_bot.last_triggered is not None
                            assert result == {'id': 'order-111', 'price': 50000.0, 'amount': 0.01}

    def test_execute_inactive_bot(self):
        mock_bot = MagicMock()
        mock_bot.is_active = False

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with pytest.raises(ValueError, match='Bot is not active'):
                BotExecutorService.execute_signal_bot_order('user1', 'bot-789', {})

    def test_execute_with_default_amount(self):
        mock_bot = MagicMock()
        mock_bot.is_active = True
        mock_bot.exchange_name = 'bybit'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.default_amount = Decimal('0.01')

        mock_creds = MagicMock()
        mock_creds.get_decrypted_credentials.return_value = {'api_key': 'k', 'secret_key': 's'}

        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {'id': 'o1', 'price': 50000.0}

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.ExchangeCredentials.objects.get', return_value=mock_creds):
                with patch('services.bot_executor.ccxt') as mock_ccxt:
                    mock_exchange_class = MagicMock(return_value=mock_exchange)
                    mock_ccxt.bybit = mock_exchange_class
                    with patch('services.bot_executor.Indicator.objects.create'):
                        with patch('services.bot_executor.Order.objects.create'):
                            BotExecutorService.execute_signal_bot_order(
                                'user1', 'bot-789',
                                {'side': 'buy'}
                            )

                            mock_exchange.create_order.assert_called_once_with(
                                symbol='BTC/USDT', type='market', side='buy', amount=0.01
                            )

    def test_execute_uses_exchange_from_bot(self):
        mock_bot = MagicMock()
        mock_bot.is_active = True
        mock_bot.exchange_name = 'binance'
        mock_bot.trading_pair = 'ETH/USDT'
        mock_bot.default_amount = Decimal('0.1')

        mock_creds = MagicMock()
        mock_creds.get_decrypted_credentials.return_value = {'api_key': 'k', 'secret_key': 's'}

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.ExchangeCredentials.objects.get', return_value=mock_creds):
                with patch('services.bot_executor.ccxt') as mock_ccxt:
                    mock_exchange_class = MagicMock()
                    mock_ccxt.binance = mock_exchange_class
                    mock_exchange = MagicMock()
                    mock_exchange.create_order.return_value = {'id': 'o1'}
                    mock_exchange_class.return_value = mock_exchange
                    with patch('services.bot_executor.Indicator.objects.create'):
                        with patch('services.bot_executor.Order.objects.create'):
                            BotExecutorService.execute_signal_bot_order(
                                'user1', 'bot-789', {'side': 'sell'}
                            )

                            mock_ccxt.binance.assert_called_once()

    def test_execute_creates_order_and_indicator(self):
        mock_bot = MagicMock()
        mock_bot.is_active = True
        mock_bot.exchange_name = 'bybit'
        mock_bot.trading_pair = 'BTC/USDT'
        mock_bot.default_amount = Decimal('0.01')

        mock_creds = MagicMock()
        mock_creds.get_decrypted_credentials.return_value = {'api_key': 'k', 'secret_key': 's'}

        mock_exchange = MagicMock()
        mock_exchange.create_order.return_value = {'id': 'o1', 'price': 50000.0}

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.ExchangeCredentials.objects.get', return_value=mock_creds):
                with patch('services.bot_executor.ccxt') as mock_ccxt:
                    mock_exchange_class = MagicMock(return_value=mock_exchange)
                    mock_ccxt.bybit = mock_exchange_class
                    with patch('services.bot_executor.Indicator.objects.create') as mock_ind:
                        with patch('services.bot_executor.Order.objects.create') as mock_order:
                            BotExecutorService.execute_signal_bot_order(
                                'user1', 'bot-789', {'side': 'buy', 'Pair': 'BTC/USDT'}
                            )

                            mock_ind.assert_called_once_with(user='user1', Pair='BTC/USDT')
                            mock_order.assert_called_once()

    def test_execute_credentials_not_found(self):
        mock_bot = MagicMock()
        mock_bot.is_active = True
        mock_bot.exchange_name = 'bybit'

        with patch('services.bot_executor.SignalBot.objects.get', return_value=mock_bot):
            with patch('services.bot_executor.ExchangeCredentials.objects.get', side_effect=Exception('No creds')):
                with pytest.raises(Exception, match='No creds'):
                    BotExecutorService.execute_signal_bot_order('user1', 'bot-789', {'side': 'buy'})
