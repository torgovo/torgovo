"""
Business logic for executing bot orders.
Bridges Django admin/views with the BotEngine trading engine.
"""
import logging
from django.utils import timezone
from apps.bots.models import GridBot, MartingaleBot, SignalBot, Order, Indicator

logger = logging.getLogger(__name__)


class BotExecutorService:
    """Service for starting/stopping bots from admin or API views."""

    @staticmethod
    def start_grid_bot(user, grid_bot_id: str):
        """Start a grid bot via Celery task."""
        from apps.trading.tasks import run_trading_bot

        grid_bot = GridBot.objects.get(id=grid_bot_id, user=user)

        if not grid_bot.subscription or grid_bot.subscription.status != 'active':
            raise ValueError("No active subscription for this bot")

        # Dispatch to Celery
        run_trading_bot.delay(str(grid_bot.id), bot_type='grid')

        grid_bot.is_running = True
        grid_bot.started_at = timezone.now()
        grid_bot.save(update_fields=['is_running', 'started_at', 'updated_at'])
        logger.info(f"Grid bot {grid_bot.bot_name} started")
        return True

    @staticmethod
    def stop_grid_bot(user, grid_bot_id: str):
        """Stop a grid bot."""
        from apps.trading.tasks import stop_bot

        grid_bot = GridBot.objects.get(id=grid_bot_id, user=user)

        # Dispatch stop task
        stop_bot.delay(str(grid_bot.id), bot_type='grid')

        grid_bot.is_running = False
        grid_bot.stopped_at = timezone.now()
        grid_bot.save(update_fields=['is_running', 'stopped_at', 'updated_at'])
        logger.info(f"Grid bot {grid_bot.bot_name} stopped")
        return True

    @staticmethod
    def start_martingale_bot(user, bot_id: str):
        """Start a martingale bot via Celery task."""
        from apps.trading.tasks import run_trading_bot

        bot = MartingaleBot.objects.get(id=bot_id, user=user)

        if not bot.subscription or bot.subscription.status != 'active':
            raise ValueError("No active subscription for this bot")

        run_trading_bot.delay(str(bot.id), bot_type='martingale')

        bot.is_running = True
        bot.started_at = timezone.now()
        bot.save(update_fields=['is_running', 'started_at', 'updated_at'])
        logger.info(f"Martingale bot {bot.bot_name} started")
        return True

    @staticmethod
    def stop_martingale_bot(user, bot_id: str):
        """Stop a martingale bot."""
        from apps.trading.tasks import stop_bot

        bot = MartingaleBot.objects.get(id=bot_id, user=user)

        stop_bot.delay(str(bot.id), bot_type='martingale')

        bot.is_running = False
        bot.stopped_at = timezone.now()
        bot.save(update_fields=['is_running', 'stopped_at', 'updated_at'])
        logger.info(f"Martingale bot {bot.bot_name} stopped")
        return True

    @staticmethod
    def execute_signal_bot_order(user, bot_id: str, webhook_payload: dict):
        """Execute order from TradingView webhook for signal bot."""
        from apps.exchanges.models import ExchangeCredentials
        import ccxt

        bot = SignalBot.objects.get(id=bot_id, user=user, is_deleted=False)

        if not bot.is_active:
            raise ValueError("Bot is not active")

        side = webhook_payload.get('side', '').lower()
        trading_pair = webhook_payload.get('Pair', bot.trading_pair)
        amount = float(webhook_payload.get('position_size', bot.default_amount))

        # Get exchange credentials
        credentials = ExchangeCredentials.objects.get(
            user=user, exchange_name=bot.exchange_name, is_active=True
        )
        creds = credentials.get_decrypted_credentials()

        # Execute via raw CCXT (same pattern as bot_engine.py)
        exchange_class = getattr(ccxt, bot.exchange_name.lower())
        exchange = exchange_class({
            'apiKey': creds['api_key'],
            'secret': creds['secret_key'],
            'enableRateLimit': True,
        })
        exchange.load_markets()

        order = exchange.create_order(
            symbol=trading_pair, type='market', side=side, amount=amount
        )

        # Log
        indicator = Indicator.objects.create(user=user, Pair=trading_pair)
        Order.objects.create(
            user=user, Pair=trading_pair, Indicators=indicator,
            signal_bot=bot, Side=side.upper(), Category='signal_bot',
            Order_type='market', Quantity=amount,
            Price=order.get('price'), Exchange=bot.exchange_name,
            Description='Signal bot webhook execution', Details=order,
        )

        bot.total_trades += 1
        bot.last_triggered = timezone.now()
        bot.save()

        logger.info(f"Signal bot order executed: {side} {amount} {trading_pair}")
        return order