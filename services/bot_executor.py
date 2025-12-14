"""
Business logic for executing bot orders using TradingManager.
Handles validation, order creation, and logging.
"""

import logging
from decimal import Decimal
from django.utils import timezone
from apps.payments.models import BotSubscription
from apps.bots.models import Order, Indicator, PairConfig, CustomBot
from trading.manager import trading_manager
from apps.exchanges.executor import ExchangeExecutor
from apps.exchanges.models import ExchangeCredentials

logger = logging.getLogger(__name__)


class BotExecutorService:
    """
    Service for executing trades from bots.
    """

    @staticmethod
    def execute_custom_bot_order(user, subscription_id: str, webhook_payload: dict):
        """
        Execute order from TradingView webhook for custom bot.

        Args:
            user: Django user instance
            subscription_id: BotSubscription ID
            webhook_payload: {
                "secret": "...",
                "action": "buy/sell",
                "symbol": "BTC/USDT",
                "amount": "1.5"
            }
        """
        # Verify subscription is active
        subscription = BotSubscription.objects.get(
            id=subscription_id,
            user=user,
            status='active'
        )

        # Verify secret
        if webhook_payload.get('secret') != subscription.webhook_secret:
            raise ValueError("Invalid webhook secret")

        # Verify exchange credentials exist
        exchange_name = webhook_payload.get('exchange', subscription.exchange_name)

        credentials = ExchangeCredentials.objects.get(
            user=user,
            exchange_name=exchange_name,
            is_active=True,
            verification_status='verified'
        )

        # Prepare order data
        order_data = {
            'symbol': webhook_payload['symbol'],
            'side': webhook_payload['action'],
            'type': 'market',
            'amount': Decimal(webhook_payload['amount']),
        }

        # Execute order
        result = ExchangeExecutor.execute_order(order_data, credentials)

        # Create Indicator snapshot
        indicator = Indicator.objects.create(
            user=user,
            Pair=order_data['symbol'],
            # Add indicator values if provided in webhook
        )

        # Log the order
        order = Order.objects.create(
            user=user,
            Time=timezone.now(),
            Pair=order_data['symbol'],
            Indicators=indicator,
            custom_bot=CustomBot.objects.filter(user=user, is_active=True).first(),
            Side=order_data['side'].upper(),
            Category='custom_bot',
            Order_type='market',
            Quantity=order_data['amount'],
            Price=result.get('price'),
            Exchange=exchange_name,
            Description=f"Custom bot webhook execution",
            Details=result,
        )

        # Update bot stats
        if order.custom_bot:
            order.custom_bot.total_trades += 1
            order.custom_bot.successful_trades += 1 if float(result.get('price', 0)) > 0 else 0
            order.custom_bot.save()

        logger.info(f"Custom bot order executed: {order}")
        return result

    @staticmethod
    def start_grid_bot(user, grid_bot_id: str):
        """
        Start a grid bot - validates subscription then uses TradingManager.
        """
        from apps.bots.models import GridBot

        grid_bot = GridBot.objects.get(id=grid_bot_id, user=user)

        # VALIDATE SUBSCRIPTION
        if not grid_bot.subscription or grid_bot.subscription.status != 'active':
            raise ValueError("No active subscription for this bot")

        # Get the PairConfig
        pair_config = PairConfig.objects.get(
            subscription=grid_bot.subscription,
            pair_symbol=grid_bot.trading_pair,
            bot_type='grid'
        )

        # Prepare config for TradingManager
        config = {
            'bot_name': grid_bot.bot_name,
            'exchange_name': grid_bot.exchange_name,
            'trading_pair': grid_bot.trading_pair,
            'base_amount': float(grid_bot.base_amount),
            'favor_levels': grid_bot.favor_levels,
            'against_levels': grid_bot.against_levels,
            'bot_type': 'grid',
            'pair_config': pair_config,
        }

        # Use TradingManager
        bot = trading_manager.create_bot(user, 'grid', config)
        if bot:
            success = trading_manager.start_bot(user, 'grid', config)
            if success:
                grid_bot.is_running = True
                grid_bot.started_at = timezone.now()
                grid_bot.save()
                return True

        return False

    @staticmethod
    def stop_grid_bot(user, grid_bot_id: str):
        """Stop a grid bot"""
        from apps.bots.models import GridBot

        grid_bot = GridBot.objects.get(id=grid_bot_id, user=user)

        config = {
            'bot_name': grid_bot.bot_name,
            'exchange_name': grid_bot.exchange_name,
            'trading_pair': grid_bot.trading_pair,
            'bot_type': 'grid',
        }

        success = trading_manager.stop_bot(user, 'grid', config)

        if success:
            grid_bot.is_running = False
            grid_bot.stopped_at = timezone.now()
            grid_bot.save()

        return success

    @staticmethod
    def refresh_bot_config(user, bot_type: str, pair_symbol: str):
        """Refresh bot configuration from database"""
        config = {
            'trading_pair': pair_symbol,
            'bot_type': bot_type,
            'bot_name': 'refresh',
        }
        return trading_manager.refresh_bot_config(user, bot_type, config)