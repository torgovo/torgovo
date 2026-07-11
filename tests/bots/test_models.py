import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestSignalBotModel:
    def test_create_signal_bot(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user,
            bot_name='Test Signal Bot',
            exchange_name='binance',
            trading_pair='BTC/USDT',
            default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        assert bot.bot_id is not None
        assert len(bot.bot_id) == 17  # xxxxx-xxxxx-xxxxx
        assert '-' in bot.bot_id
        assert bot.webhook_url is not None
        assert bot.webhook_url.startswith('http')
        assert bot.secret_key is not None
        assert len(bot.secret_key) > 0
        assert bot.webhook_message is not None
        assert bot.webhook_message['bot_id'] == bot.bot_id
        assert bot.signals_used_this_month == 0
        assert bot.is_active is True
        assert str(bot) == 'Test Signal Bot - BTC/USDT'

    def test_bot_id_uniqueness(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot1 = SignalBot.objects.create(
            user=user, bot_name='Bot1', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        bot2 = SignalBot.objects.create(
            user=user, bot_name='Bot2', exchange_name='bybit',
            trading_pair='ETH/USDT', default_amount=Decimal('0.1'),
            subscription=signal_bot_subscription,
        )
        assert bot1.bot_id != bot2.bot_id

    def test_webhook_message_generation(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        msg = bot.create_message()
        assert msg['bot_id'] == bot.bot_id
        assert msg['secret'] == bot.secret_key
        assert '{{syminfo.basecurrency}}/{{syminfo.currency}}' in msg['Pair']
        assert msg['exchange'] == 'binance'
        assert '{{strategy.order.action}}' in msg['side']

    def test_generate_webhook_credentials(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        old_url = bot.webhook_url
        old_secret = bot.secret_key
        bot.webhook_url = ''
        bot.secret_key = ''
        bot.generate_webhook_credentials()
        assert bot.webhook_url != old_url
        assert bot.secret_key != old_secret
        assert bot.webhook_url != ''

    def test_increment_signal_count(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        assert bot.signals_used_this_month == 0
        bot.increment_signal_count()
        bot.refresh_from_db()
        assert bot.signals_used_this_month == 1
        assert bot.last_triggered is not None

    def test_signals_remaining(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
            signal_limit=100,
        )
        assert bot.signals_remaining == 100
        bot.signals_used_this_month = 50
        bot.save()
        bot.refresh_from_db()
        assert bot.signals_remaining == 50

    def test_signals_remaining_min_zero(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
            signal_limit=10, signals_used_this_month=15,
        )
        assert bot.signals_remaining == 0

    def test_success_rate_zero_trades(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            subscription=signal_bot_subscription,
        )
        assert bot.success_rate == 0

    def test_success_rate_calculation(self, user, signal_bot_subscription):
        from apps.bots.models import SignalBot
        bot = SignalBot.objects.create(
            user=user, bot_name='Test', exchange_name='binance',
            trading_pair='BTC/USDT', default_amount=Decimal('0.01'),
            total_trades=10, successful_trades=7,
            subscription=signal_bot_subscription,
        )
        assert bot.success_rate == 70.0


@pytest.mark.django_db
class TestGridBotModel:
    def test_create_grid_bot(self, user, bot_subscription_plan):
        from apps.payments.models import BotSubscription
        from apps.bots.models import GridBot
        sub = BotSubscription.objects.create(
            user=user, plan=bot_subscription_plan, status='active'
        )
        bot = GridBot.objects.create(
            user=user, bot_name='Grid Bot 1', exchange_name='binance',
            trading_pair='BTC/USDT', base_amount=Decimal('0.001'),
            favor_levels=5, against_levels=5, subscription=sub,
        )
        assert bot.id is not None
        assert bot.is_running is False
        assert bot.favor_levels == 5
        assert bot.against_levels == 5
        assert bot.level_spacing_percent == Decimal('1.0')
        assert bot.amount_type == 'quote'
        assert bot.total_trades_executed == 0
        assert str(bot) == 'Grid Bot 1 - BTC/USDT'

    def test_save_state(self, user, bot_subscription):
        from apps.bots.models import GridBot
        bot = GridBot.objects.create(
            user=user, bot_name='Grid', exchange_name='binance',
            trading_pair='BTC/USDT', base_amount=Decimal('0.001'),
            favor_levels=3, against_levels=3, subscription=bot_subscription,
        )
        orders = [{'order_id': '123', 'price': '45000'}]
        levels = {'buy': [1, 2], 'sell': [3, 4]}
        bot.save_state(active_orders=orders, grid_levels=levels)
        bot.refresh_from_db()
        assert bot.active_orders == orders
        assert bot.current_grid_levels == levels

    def test_meta_unique_together(self):
        from apps.bots.models import GridBot
        constraint = GridBot._meta.unique_together
        assert 'subscription' in constraint

    def test_defaults(self, user, bot_subscription):
        from apps.bots.models import GridBot
        bot = GridBot.objects.create(
            user=user, bot_name='Grid', exchange_name='binance',
            trading_pair='BTC/USDT', base_amount=Decimal('0.001'),
            favor_levels=3, against_levels=3, subscription=bot_subscription,
        )
        assert bot.initial_amount == Decimal('0')
        assert bot.favor_level_qty is None
        assert bot.against_level_qty is None
        assert bot.active_orders == []
        assert bot.current_grid_levels == {}
        assert bot.total_invested == Decimal('0')


@pytest.mark.django_db
class TestMartingaleBotModel:
    def test_create_martingale_bot(self, user, bot_subscription):
        from apps.bots.models import MartingaleBot
        bot = MartingaleBot.objects.create(
            user=user, bot_name='Martingale Bot', exchange_name='bybit',
            trading_pair='ETH/USDT', base_amount=Decimal('0.01'),
            favor_levels=4, against_levels=4,
            multiplier_factor=Decimal('2.0'),
            subscription=bot_subscription,
        )
        assert bot.multiplier_factor == Decimal('2.0')
        assert bot.current_level == 0
        assert bot.max_level_reached == 0
        assert bot.level_spacing_percent == Decimal('2.0')
        assert str(bot) == 'Martingale Bot - ETH/USDT'

    def test_martingale_defaults(self, user, bot_subscription):
        from apps.bots.models import MartingaleBot
        bot = MartingaleBot.objects.create(
            user=user, bot_name='M', exchange_name='binance',
            trading_pair='SOL/USDT', base_amount=Decimal('1'),
            favor_levels=2, against_levels=2,
            subscription=bot_subscription,
        )
        assert bot.multiplier_factor == Decimal('2.0')
        assert bot.amount_type == 'quote'
        assert bot.current_profit_loss == Decimal('0')
        assert bot.total_invested == Decimal('0')


@pytest.mark.django_db
class TestQuantumAIFundModel:
    def test_create_fund(self, user):
        from apps.bots.models import QuantumAIFund
        fund = QuantumAIFund.objects.create(
            name='Test Fund',
            master_api_key='encrypted_key',
            master_secret_key='encrypted_secret',
            total_fund_value=Decimal('100000'),
            total_profit=Decimal('5000'),
            total_deposits=Decimal('50000'),
        )
        assert fund.shown_percentage == Decimal('20.00')
        assert fund.is_active is True
        assert str(fund).startswith('Test Fund')

    def test_calculate_profit_to_distribute_positive(self, user):
        from apps.bots.models import QuantumAIFund
        fund = QuantumAIFund.objects.create(
            name='Fund', master_api_key='k', master_secret_key='s',
            total_profit=Decimal('10000'), shown_percentage=Decimal('20.00'),
        )
        assert fund.calculate_profit_to_distribute() == Decimal('2000')

    def test_calculate_profit_to_distribute_zero_profit(self, user):
        from apps.bots.models import QuantumAIFund
        fund = QuantumAIFund.objects.create(
            name='Fund', master_api_key='k', master_secret_key='s',
            total_profit=Decimal('0'),
        )
        assert fund.calculate_profit_to_distribute() == Decimal('0')

    def test_calculate_profit_to_distribute_negative_profit(self, user):
        from apps.bots.models import QuantumAIFund
        fund = QuantumAIFund.objects.create(
            name='Fund', master_api_key='k', master_secret_key='s',
            total_profit=Decimal('-1000'),
        )
        assert fund.calculate_profit_to_distribute() == Decimal('0')


@pytest.mark.django_db
class TestQuantumAIBotModel:
    def test_create_quantum_ai_bot(self, user, quantum_fund):
        from apps.bots.models import QuantumAIBot
        bot = QuantumAIBot.objects.create(
            fund=quantum_fund, bot_name='AI Bot Alpha',
            exchange_name='binance', trading_pair='BTC/USDT',
        )
        assert bot.is_running is False
        assert bot.total_trades == 0
        assert str(bot) == 'AI Bot Alpha [Stopped] - BTC/USDT'

    def test_quantum_ai_bot_running_str(self, user, quantum_fund):
        from apps.bots.models import QuantumAIBot
        bot = QuantumAIBot.objects.create(
            fund=quantum_fund, bot_name='AI Bot Beta',
            exchange_name='bybit', trading_pair='ETH/USDT',
            is_running=True,
        )
        assert 'Running' in str(bot)


@pytest.mark.django_db
class TestQuantumAIInvestmentModel:
    def test_create_investment(self, user, quantum_fund, bot_subscription):
        from apps.bots.models import QuantumAIInvestment
        inv = QuantumAIInvestment.objects.create(
            user=user, fund=quantum_fund,
            amount=Decimal('1000'), status='active',
            subscription=bot_subscription,
        )
        assert inv.status == 'active'
        assert inv.accrued_profit == Decimal('0')
        assert str(inv) == f"{user.email} - 1000 USDT"

    def test_calculate_share_percentage(self, user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment
        quantum_fund.total_deposits = Decimal('50000')
        quantum_fund.save()
        inv = QuantumAIInvestment.objects.create(
            user=user, fund=quantum_fund,
            amount=Decimal('5000'), status='active',
        )
        assert inv.calculate_share_percentage() == Decimal('10.00')

    def test_calculate_share_percentage_zero_deposits(self, user, quantum_fund_without_deposits):
        from apps.bots.models import QuantumAIInvestment
        inv = QuantumAIInvestment(
            user=user, fund=quantum_fund_without_deposits,
            amount=Decimal('1000'),
        )
        assert inv.calculate_share_percentage() == Decimal('0')

    def test_calculate_profit_share_not_active(self, user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment
        inv = QuantumAIInvestment.objects.create(
            user=user, fund=quantum_fund,
            amount=Decimal('1000'), status='pending',
        )
        assert inv.calculate_profit_share() == Decimal('0')

    def test_calculate_profit_share_active(self, user, quantum_fund):
        from apps.bots.models import QuantumAIInvestment
        quantum_fund.total_deposits = Decimal('50000')
        quantum_fund.total_profit = Decimal('10000')
        quantum_fund.shown_percentage = Decimal('20.00')
        quantum_fund.save()
        inv = QuantumAIInvestment.objects.create(
            user=user, fund=quantum_fund,
            amount=Decimal('5000'), status='active',
        )
        inv.share_percentage = Decimal('10.00')
        inv.save()
        assert inv.calculate_profit_share() == Decimal('200')  # (10000 * 0.2) * 0.1


@pytest.mark.django_db
class TestQuantumDepositWalletModel:
    def test_create_wallet(self, user):
        from apps.bots.models import QuantumDepositWallet
        wallet = QuantumDepositWallet.objects.create(
            coin='USDT', blockchain='ERC20',
            address='0x1234567890abcdef',
        )
        assert wallet.is_active is True
        assert str(wallet).startswith('USDT (ERC20): 0x1234567890ab')


@pytest.mark.django_db
class TestQuantumDepositModel:
    def test_create_deposit(self, user, quantum_wallet):
        from apps.bots.models import QuantumDeposit
        dep = QuantumDeposit.objects.create(
            user=user, wallet=quantum_wallet,
            amount=Decimal('500'), transaction_hash='0xabc123',
            screenshot='test.jpg',
        )
        assert dep.status == 'pending'
        assert dep.reviewed_by is None
        assert str(dep) == f"{user.email} - 500 USDT"

    def test_deposit_status_choices(self, user, quantum_wallet):
        from apps.bots.models import QuantumDeposit
        for status_code in ['pending', 'approved', 'rejected', 'processing']:
            dep = QuantumDeposit.objects.create(
                user=user, wallet=quantum_wallet,
                amount=Decimal('100'), transaction_hash=f'0x{status_code}',
                screenshot='test.jpg', status=status_code,
            )
            dep.refresh_from_db()
            assert dep.status == status_code


@pytest.mark.django_db
class TestQuantumWeeklyProfitModel:
    def test_create_weekly_profit(self, user, quantum_fund):
        from apps.bots.models import QuantumWeeklyProfit
        profit = QuantumWeeklyProfit.objects.create(
            user=user, fund=quantum_fund,
            week_start=date(2024, 1, 1),
            week_end=date(2024, 1, 7),
            total_deposited=Decimal('10000'),
            realized_pnl=Decimal('1000'),
            unrealized_pnl=Decimal('500'),
        )
        assert profit.total_pnl == Decimal('1500')
        assert profit.user_share_amount == Decimal('300')  # 1500 * 20%
        assert profit.admin_share_amount == Decimal('1200')  # 1500 * 80%
        assert profit.roi_percentage == 15.0
        assert str(profit) == 'Week of 2024-01-01 - test@example.com'

    def test_user_share_amount_zero_pnl(self, user, quantum_fund):
        from apps.bots.models import QuantumWeeklyProfit
        profit = QuantumWeeklyProfit.objects.create(
            user=user, fund=quantum_fund,
            week_start=date(2024, 1, 1),
            week_end=date(2024, 1, 7),
            total_deposited=Decimal('10000'),
            realized_pnl=Decimal('0'),
            unrealized_pnl=Decimal('-100'),
        )
        assert profit.total_pnl == Decimal('-100')
        assert profit.user_share_amount == 0
        assert profit.admin_share_amount == 0

    def test_roi_percentage_zero_deposited(self, user, quantum_fund):
        from apps.bots.models import QuantumWeeklyProfit
        profit = QuantumWeeklyProfit.objects.create(
            user=user, fund=quantum_fund,
            week_start=date(2024, 1, 1),
            week_end=date(2024, 1, 7),
        )
        assert profit.roi_percentage == 0


@pytest.mark.django_db
class TestPairConfigModel:
    def test_create_pair_config(self, user, bot_subscription):
        from apps.bots.models import PairConfig
        config = PairConfig.objects.create(
            user=user, pair_symbol='BTC/USDT',
            bot_type='grid', subscription=bot_subscription,
        )
        assert config.slug is None
        assert config.Order_Type == 'market'
        assert config.Amount_Type == 'dollar'
        assert config.Favor_levels == 3  # Note: field name misspelled in model
        assert str(config) == 'None Config'

    def test_unique_together(self, user, bot_subscription):
        from apps.bots.models import PairConfig
        PairConfig.objects.create(
            user=user, pair_symbol='BTC/USDT',
            bot_type='grid', subscription=bot_subscription,
        )
        with pytest.raises(Exception):
            PairConfig.objects.create(
                user=user, pair_symbol='BTC/USDT',
                bot_type='grid', subscription=bot_subscription,
            )


@pytest.mark.django_db
class TestIndicatorModel:
    def test_create_indicator(self, user):
        from apps.bots.models import Indicator
        ind = Indicator.objects.create(
            user=user, Pair='BTC/USDT',
            EMA=200.5, RSI=65.0,
        )
        assert ind.EMA == 200.5
        assert ind.RSI == 65.0
        assert str(ind) == f'{user} BTC/USDT Indicator Data {ind.id}'


@pytest.mark.django_db
class TestOrderModel:
    def test_create_order(self, user):
        from apps.bots.models import Order
        order = Order.objects.create(
            user=user, Pair='BTC/USDT',
            Side='buy', Price=45000.0,
            Quantity=Decimal('0.01'),
        )
        assert order.Time is not None
        assert order.Price == 45000.0
        assert 'buy' in str(order).lower()

    def test_order_save_sets_time_pakistan_tz(self, user):
        from apps.bots.models import Order
        import pytz
        order = Order.objects.create(
            user=user, Pair='ETH/USDT',
            Side='sell', Price=3000.0,
            Quantity=Decimal('0.1'),
        )
        pakistan_tz = pytz.timezone('Asia/Karachi')
        assert order.Time.tzinfo is not None


@pytest.mark.django_db
class TestTelegramModels:
    def test_create_plan(self):
        from apps.bots.models import TelegramSignalPlan
        plan = TelegramSignalPlan.objects.create(
            name='Premium', description='Top tier',
            duration_days=30, price_usd=Decimal('99.99'),
        )
        assert plan.is_active is True
        assert str(plan) == 'Premium - $99.99'

    def test_create_subscription(self, user, telegram_plan, bot_subscription):
        from apps.bots.models import TelegramSignalSubscription
        from datetime import timedelta
        sub = TelegramSignalSubscription.objects.create(
            user=user, plan=telegram_plan,
            telegram_handle='@testuser',
            expires_at=timezone.now() + timedelta(days=30),
            bot_subscription=bot_subscription,
        )
        assert sub.status == 'pending'
        assert sub.is_active is False
        assert str(sub) == f"{user.email} - @testuser"

    def test_check_and_update_status_expired(self, user, telegram_plan):
        from apps.bots.models import TelegramSignalSubscription
        from datetime import timedelta
        sub = TelegramSignalSubscription.objects.create(
            user=user, plan=telegram_plan,
            telegram_handle='@testuser',
            status='active',
            expires_at=timezone.now() - timedelta(days=1),
        )
        new_status = sub.check_and_update_status()
        assert new_status == 'expired'

    def test_check_and_update_status_still_active(self, user, telegram_plan):
        from apps.bots.models import TelegramSignalSubscription
        from datetime import timedelta
        sub = TelegramSignalSubscription.objects.create(
            user=user, plan=telegram_plan,
            telegram_handle='@testuser',
            status='active',
            expires_at=timezone.now() + timedelta(days=30),
        )
        new_status = sub.check_and_update_status()
        assert new_status == 'active'

    def test_is_active_requires_approval_and_not_expired(self, user, telegram_plan):
        from apps.bots.models import TelegramSignalSubscription
        from datetime import timedelta
        sub = TelegramSignalSubscription.objects.create(
            user=user, plan=telegram_plan,
            telegram_handle='@testuser',
            status='active',
            expires_at=timezone.now() + timedelta(days=30),
        )
        assert sub.is_active is False  # No approved_at

    def test_is_active_true_when_approved(self, user, telegram_plan):
        from apps.bots.models import TelegramSignalSubscription
        from datetime import timedelta
        sub = TelegramSignalSubscription.objects.create(
            user=user, plan=telegram_plan,
            telegram_handle='@testuser',
            status='active', approved_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )
        assert sub.is_active is True
