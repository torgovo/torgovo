import pytest
from decimal import Decimal
from django.utils import timezone
from apps.investments.models import (
    Exchange, TradingPair, ExchangeCredential, BotBase,
    WebhookAlertBot, GridBot, MartingaleBot, QuantumAIBot,
    Order, Position, TechnicalIndicator, UserBalance,
)


@pytest.mark.django_db
class TestInvestmentExchangeModel:
    def test_create_exchange(self):
        exchange = Exchange.objects.create(
            name='binance',
            display_name='Binance',
            status='active',
            api_base_url='https://api.binance.com',
        )
        assert exchange.name == 'binance'
        assert exchange.display_name == 'Binance'
        assert exchange.status == 'active'
        assert exchange.requires_passphrase is False
        assert str(exchange) == 'Binance'

    def test_exchange_unique_name(self, db):
        Exchange.objects.create(name='bybit', display_name='Bybit')
        with pytest.raises(Exception):
            Exchange.objects.create(name='bybit', display_name='Bybit Copy')

    def test_status_choices(self, db):
        for status_val in ['active', 'maintenance', 'inactive']:
            ex = Exchange.objects.create(
                name=f'ex_{status_val}', display_name=status_val, status=status_val,
            )
            assert ex.status == status_val


@pytest.mark.django_db
class TestInvestmentTradingPairModel:
    def test_create_pair(self):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_active=True,
        )
        assert pair.exchange == exchange
        assert pair.symbol == 'BTC/USDT'
        assert pair.is_active is True
        assert pair.current_price is None
        assert str(pair) == 'BTC/USDT on binance'

    def test_unique_together(self):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        TradingPair.objects.create(exchange=exchange, symbol='ETH/USDT', base_asset='ETH', quote_asset='USDT')
        with pytest.raises(Exception):
            TradingPair.objects.create(exchange=exchange, symbol='ETH/USDT', base_asset='ETH', quote_asset='USDT')


@pytest.mark.django_db
class TestInvestmentExchangeCredentialModel:
    def test_create_credential(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        cred = ExchangeCredential.objects.create(
            user=user,
            exchange=exchange,
            api_key='encrypted-key',
            secret_key='encrypted-secret',
            is_testnet=True,
        )
        assert cred.user == user
        assert cred.exchange == exchange
        assert cred.is_testnet is True
        assert cred.is_connected is False
        assert str(cred) == f'{user} — Binance'

    def test_unique_together(self, user):
        exchange = Exchange.objects.create(name='bybit', display_name='Bybit')
        ExchangeCredential.objects.create(
            user=user, exchange=exchange, api_key='k1', secret_key='s1',
        )
        with pytest.raises(Exception):
            ExchangeCredential.objects.create(
                user=user, exchange=exchange, api_key='k2', secret_key='s2',
            )


@pytest.mark.django_db
class TestBotBaseModel:
    def test_create_bot_base(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        bot = BotBase.objects.create(
            user=user, bot_name='Test Bot', category='webhook',
            exchange=exchange, trading_pair=pair,
        )
        assert bot.user == user
        assert bot.bot_name == 'Test Bot'
        assert bot.category == 'webhook'
        assert bot.status == 'idle'
        assert bot.is_active is True
        assert bot.total_trades == 0
        assert bot.total_profit_loss == Decimal('0')
        assert str(bot) == 'Test Bot (webhook)'


@pytest.mark.django_db
class TestWebhookAlertBotModel:
    def test_create_webhook_bot(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        bot = WebhookAlertBot.objects.create(
            user=user, bot_name='Webhook Bot', category='webhook',
            exchange=exchange, trading_pair=pair,
            default_amount=Decimal('50.00000000'),
        )
        assert bot.webhook_id is not None
        assert bot.default_amount == Decimal('50.00000000')
        assert str(bot) == 'Webhook Bot: Webhook Bot'


@pytest.mark.django_db
class TestGridBotModel:
    def test_create_grid_bot(self, user):
        exchange = Exchange.objects.create(name='bybit', display_name='Bybit')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='ETH/USDT', base_asset='ETH', quote_asset='USDT',
        )
        bot = GridBot.objects.create(
            user=user, bot_name='Grid Bot', category='grid',
            exchange=exchange, trading_pair=pair,
            base_amount=Decimal('100'), favor_levels=5, against_levels=5,
        )
        assert bot.base_amount == Decimal('100')
        assert bot.favor_levels == 5
        assert bot.against_levels == 5
        assert bot.current_grid_level == 0
        assert str(bot) == 'Grid Bot: Grid Bot'


@pytest.mark.django_db
class TestMartingaleBotModel:
    def test_create_martingale_bot(self, user):
        exchange = Exchange.objects.create(name='okx', display_name='OKX')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        bot = MartingaleBot.objects.create(
            user=user, bot_name='Martingale Bot', category='martingale',
            exchange=exchange, trading_pair=pair,
            multiplier_factor=Decimal('2.0'),
        )
        assert bot.multiplier_factor == Decimal('2.0')
        assert bot.current_level == 0
        assert bot.consecutive_losses == 0
        assert str(bot) == 'Martingale Bot: Martingale Bot'


@pytest.mark.django_db
class TestQuantumAIBotModel:
    def test_create_quantum_bot(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        bot = QuantumAIBot.objects.create(
            user=user, bot_name='Quantum Bot', category='quantum_ai',
            exchange=exchange, trading_pair=pair,
            auto_compound=True, compound_frequency='weekly', risk_level='medium',
        )
        assert bot.auto_compound is True
        assert bot.compound_frequency == 'weekly'
        assert bot.risk_level == 'medium'
        assert bot.blockchain_addresses == {}
        assert str(bot) == 'Quantum AI Bot: Quantum Bot'


@pytest.mark.django_db
class TestInvestmentOrderModel:
    def test_create_order(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        order = Order.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            order_type='market',
            side='buy',
            quantity=Decimal('0.00100000'),
            price=Decimal('50000.00000000'),
        )
        assert order.user == user
        assert order.order_type == 'market'
        assert order.side == 'buy'
        assert order.status == 'pending'
        assert order.quantity == Decimal('0.00100000')
        assert str(order) == 'buy 0.00100000 @ 50000.00000000'

    def test_save_syncs_aliases(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        order = Order.objects.create(
            user=user, exchange=exchange, trading_pair=pair,
            order_type='limit', side='sell',
            quantity=Decimal('1'), price=Decimal('100'),
            description='Test order',
        )
        assert order.Side == 'sell'
        assert order.Description == 'Test order'


@pytest.mark.django_db
class TestInvestmentPositionModel:
    def test_create_position(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        position = Position.objects.create(
            user=user,
            exchange=exchange,
            trading_pair=pair,
            side='long',
            entry_price=Decimal('50000.00000000'),
            quantity=Decimal('0.10000000'),
            leverage=1,
        )
        assert position.user == user
        assert position.side == 'long'
        assert position.entry_price == Decimal('50000.00000000')
        assert position.leverage == 1
        assert position.unrealized_pnl == Decimal('0')
        assert str(position) == 'long 0.10000000 @ 50000.00000000'


@pytest.mark.django_db
class TestTechnicalIndicatorModel:
    def test_create_indicator(self):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        pair = TradingPair.objects.create(
            exchange=exchange, symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT',
        )
        indicator = TechnicalIndicator.objects.create(
            indicator_type='RSI',
            trading_pair=pair,
            exchange=exchange,
            values={'RSI': 72.5, 'PrevRSI': 65.0},
            color='red',
            prev_color='green',
            triggered_at=timezone.now(),
        )
        assert indicator.indicator_type == 'RSI'
        assert indicator.values == {'RSI': 72.5, 'PrevRSI': 65.0}
        assert indicator.color == 'red'
        assert str(indicator) == f'RSI — {pair}'


@pytest.mark.django_db
class TestUserBalanceModel:
    def test_create_balance(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        balance = UserBalance.objects.create(
            user=user,
            exchange=exchange,
            currency='USDT',
            available=Decimal('1000.00000000'),
            locked=Decimal('500.00000000'),
            total=Decimal('1500.00000000'),
        )
        assert balance.user == user
        assert balance.currency == 'USDT'
        assert balance.available == Decimal('1000.00000000')
        assert balance.total == Decimal('1500.00000000')
        assert str(balance) == f'{user} — USDT: 1500.00000000'

    def test_unique_together(self, user):
        exchange = Exchange.objects.create(name='binance', display_name='Binance')
        UserBalance.objects.create(
            user=user, exchange=exchange, currency='USDT',
            available=Decimal('100'), total=Decimal('100'),
        )
        with pytest.raises(Exception):
            UserBalance.objects.create(
                user=user, exchange=exchange, currency='USDT',
                available=Decimal('200'), total=Decimal('200'),
            )
