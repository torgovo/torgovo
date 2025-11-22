"""
Webhook views for TradingView integration
"""
import json
import time
import hmac
import hashlib
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from rest_framework import status
from apps.bots.models import WebhookAlert, Order
from apps.webhooks.models import WebhookLog
from core.exceptions import TradingBotException
from core.utils import get_client_ip, validate_webhook_signature

logger = logging.getLogger('webhooks')


@method_decorator(csrf_exempt, name='dispatch')
class TradingViewWebhookView(View):
    """
    Webhook endpoint for TradingView alerts.
    Processes trading signals and executes orders on configured exchanges.
    """

    def post(self, request, webhook_id):
        """Process TradingView webhook request."""
        start_time = time.time()
        webhook_log = None

        try:
            # Parse request body
            raw_data = request.body.decode('utf-8').strip('"')
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                payload = json.loads(raw_data.replace("'", '"'))

            # Get webhook configuration
            try:
                webhook_alert = WebhookAlert.objects.get(
                    id=webhook_id,
                    is_active=True,
                    is_deleted=False
                )
            except WebhookAlert.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid or inactive webhook ID',
                    'webhook_id': webhook_id
                }, status=status.HTTP_404_NOT_FOUND)

            # Verify secret key
            if not self.verify_secret_key(payload, webhook_alert.secret_key):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid secret key'
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Create webhook log
            webhook_log = WebhookLog.objects.create(
                user=webhook_alert.user,
                webhook_id=webhook_id,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                payload=payload,
            )

            # Process webhook signal
            result = self.process_trading_signal(payload, webhook_alert)

            # Update webhook statistics
            webhook_alert.total_trades += 1
            if result['success']:
                webhook_alert.successful_trades += 1
                webhook_alert.total_profit_loss += Decimal(str(result.get('profit_loss', 0)))
            webhook_alert.last_triggered = webhook_alert.updated_at = webhook_log.created_at
            webhook_alert.save()

            # Update webhook log
            processing_time = int((time.time() - start_time) * 1000)
            webhook_log.response_status = 200
            webhook_log.processing_time_ms = processing_time
            webhook_log.is_successful = result['success']
            webhook_log.save()

            return JsonResponse({
                'status': 'success' if result['success'] else 'error',
                'message': result['message'],
                'order_id': result.get('order_id'),
                'executed_price': result.get('executed_price'),
                'executed_amount': result.get('executed_amount'),
                'processing_time_ms': processing_time
            }, status=status.HTTP_200_OK)

        except Exception as e:
            error_message = str(e)
            logger.error(f"Webhook processing error: {error_message}")

            # Update webhook log if it exists
            if webhook_log:
                processing_time = int((time.time() - start_time) * 1000)
                webhook_log.response_status = 500
                webhook_log.processing_time_ms = processing_time
                webhook_log.is_successful = False
                webhook_log.error_message = error_message
                webhook_log.save()

            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error',
                'error': error_message
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def verify_secret_key(self, payload: dict, secret_key: str) -> bool:
        """Verify webhook secret key."""
        try:
            webhook_secret = payload.get('secret', '')
            return webhook_secret == secret_key

        except Exception:
            return False

    def process_trading_signal(self, payload: dict, webhook_alert: WebhookAlert) -> dict:
        """Process trading signal and execute order."""
        try:
            # Extract signal data
            action = payload.get('action', '').lower()
            tv_exchange = payload.get('tv_exchange', '').lower()
            tv_instrument = payload.get('tv_instrument', '')
            trigger_price = Decimal(str(payload.get('trigger_price', 0)))
            order_data = payload.get('order', {})
            bot_uuid = payload.get('bot_uuid', '')

            # Validate signal
            if action not in ['buy', 'sell']:
                raise TradingBotException(
                    message=f"Invalid action: {action}",
                    error_code='INVALID_ACTION'
                )

            if tv_exchange != webhook_alert.exchange_name:
                raise TradingBotException(
                    message=f"Exchange mismatch: {tv_exchange} vs {webhook_alert.exchange_name}",
                    error_code='EXCHANGE_MISMATCH'
                )

            # Normalize trading pair
            trading_pair = self.normalize_trading_pair(tv_instrument)
            if trading_pair != webhook_alert.trading_pair:
                raise TradingBotException(
                    message=f"Trading pair mismatch: {trading_pair} vs {webhook_alert.trading_pair}",
                    error_code='PAIR_MISMATCH'
                )

            # Get order amount
            order_amount = Decimal(str(order_data.get('amount', webhook_alert.default_amount)))

            # Get exchange credentials
            exchange_creds = webhook_alert.user.profile.get_exchange_credential(webhook_alert.exchange_name)
            if not exchange_creds:
                raise TradingBotException(
                    message=f"No exchange credentials for {webhook_alert.exchange_name}",
                    error_code='NO_CREDENTIALS'
                )

            # Initialize exchange bot
            from trading.exchanges import BinanceBot, BybitBot, OKXBot, MEXCBot, AlpacaBot

            exchange_bots = {
                'binance': BinanceBot,
                'bybit': BybitBot,
                'okx': OKXBot,
                'mexc': MEXCBot,
                'alpaca': AlpacaBot,
            }

            bot_class = exchange_bots.get(webhook_alert.exchange_name.lower())
            if not bot_class:
                raise TradingBotException(
                    message=f"Unsupported exchange: {webhook_alert.exchange_name}",
                    error_code='UNSUPPORTED_EXCHANGE'
                )

            # Get exchange credentials model
            from apps.exchanges.models import ExchangeCredentials
            creds_model = ExchangeCredentials.objects.get(
                user=webhook_alert.user,
                exchange_name=webhook_alert.exchange_name,
                is_active=True
            )

            exchange_bot = bot_class(webhook_alert.user, creds_model)

            # Execute order
            order_result = self.execute_order(
                exchange_bot,
                trading_pair,
                action,
                order_amount,
                webhook_alert,
                payload
            )

            return {
                'success': True,
                'message': f'Order executed successfully',
                'order_id': order_result.get('order_id'),
                'executed_price': order_result.get('executed_price'),
                'executed_amount': order_result.get('executed_amount'),
                'profit_loss': order_result.get('profit_loss', 0),
            }

        except TradingBotException as e:
            return {
                'success': False,
                'message': e.message,
                'error_code': e.error_code,
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Error processing trading signal: {str(e)}",
            }

    def execute_order(self, exchange_bot, trading_pair: str, side: str, amount: Decimal,
                      webhook_alert: WebhookAlert, payload: dict) -> dict:
        """Execute trading order."""
        try:
            # Create market order
            order = exchange_bot.create_market_order(
                symbol=trading_pair,
                side=side,
                float(amount)
            )

            # Calculate take profit and stop loss prices
            executed_price = Decimal(str(order.get('price', 0)))
            if executed_price == 0:
                executed_price = Decimal(str(payload.get('trigger_price', 0)))

            take_profit_price = None
            stop_loss_price = None

            if side == 'buy':
                # For buy orders, TP is higher, SL is lower
                tp_multiplier = 1 + (webhook_alert.take_profit_percent / 100)
                sl_multiplier = 1 - (webhook_alert.stop_loss_percent / 100)
                take_profit_price = executed_price * tp_multiplier
                stop_loss_price = executed_price * sl_multiplier
            else:
                # For sell orders, TP is lower, SL is higher
                tp_multiplier = 1 - (webhook_alert.take_profit_percent / 100)
                sl_multiplier = 1 + (webhook_alert.stop_loss_percent / 100)
                take_profit_price = executed_price * tp_multiplier
                stop_loss_price = executed_price * sl_multiplier

            # Store order in database
            db_order = Order.objects.create(
                user=webhook_alert.user,
                pair=trading_pair,
                exchange=webhook_alert.exchange_name,
                side=side,
                category='webhook',
                order_type='market',
                quantity=amount,
                price=executed_price,
                executed_price=Decimal(str(order.get('price', executed_price))),
                exchange_order_id=order.get('id', ''),
                status=order.get('status', 'filled'),
                take_profit=take_profit_price,
                stop_loss=stop_loss_price,
                description=f"TradingView webhook signal: {payload.get('strategy', {}).get('market_position', 'Unknown')}",
                details={
                    'webhook_id': str(webhook_alert.id),
                    'bot_uuid': payload.get('bot_uuid'),
                    'strategy_info': payload.get('strategy_info', {}),
                    'tv_exchange': payload.get('tv_exchange'),
                    'tv_instrument': payload.get('tv_instrument'),
                    'trigger_price': str(payload.get('trigger_price')),
                }
            )

            return {
                'order_id': order.get('id', ''),
                'executed_price': float(executed_price),
                'executed_amount': float(order.get('filled', amount)),
                'order_status': order.get('status', 'filled'),
                'fees': order.get('fee', {}).get('cost', 0),
            }

        except Exception as e:
            logger.error(f"Order execution error: {e}")
            raise TradingBotException(
                message=f"Order execution failed: {str(e)}",
                error_code='ORDER_EXECUTION_FAILED'
            )

    def normalize_trading_pair(self, tv_instrument: str) -> str:
        """Normalize TradingView instrument to exchange format."""
        # Common conversions
        conversions = {
            'BTCUSD': 'BTC/USDT',
            'ETHUSD': 'ETH/USDT',
            'BTCUSDT': 'BTC/USDT',
            'ETHUSDT': 'ETH/USDT',
        }

        # Check if already in correct format
        if '/' in tv_instrument:
            return tv_instrument

        # Apply conversions
        return conversions.get(tv_instrument, f"{tv_instrument}/USDT")


@method_decorator(csrf_exempt, name='dispatch')
class EMAIndicatorView(View):
    """
    Webhook endpoint for EMA (Exponential Moving Average) indicators.
    Used for Quantum AI bot technical analysis.
    """

    def post(self, request):
        """Process EMA indicator signal."""
        try:
            # Parse request data
            raw_data = request.body.decode('utf-8').strip('"')
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = json.loads(raw_data.replace("'", '"'))

            # Extract EMA data
            ema_value = data.get('EMA200')  # Default to EMA200
            if not ema_value:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No EMA value found in request'
                }, status=status.HTTP_400_BAD_REQUEST)

            username = data.get('username')
            pair = data.get('pair')
            exchange = data.get('exchange', 'binance')

            if not all([username, pair]):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing required fields: username, pair'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Process EMA signal
            result = self.process_ema_signal(ema_value, username, pair, exchange)

            return JsonResponse({
                'status': 'success',
                'message': f'EMA processed for {pair}',
                'ema_value': ema_value,
                'bot_updated': result['bot_updated']
            })

        except Exception as e:
            logger.error(f"EMA processing error: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'EMA processing failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def process_ema_signal(self, ema_value: float, username: str, pair: str, exchange: str) -> dict:
        """Process EMA signal for Quantum AI bot."""
        try:
            from django.contrib.auth import get_user_model
            from apps.bots.models import QuantumAIBot, TechnicalIndicator

            User = get_user_model()

            # Get user
            user = User.objects.get(username=username)

            # Get Quantum AI bot
            quantum_bot = QuantumAIBot.objects.filter(
                user=user,
                is_active=True,
                is_deleted=False
            ).first()

            if not quantum_bot:
                return {'bot_updated': False, 'message': 'No active Quantum AI bot found'}

            # Store technical indicator
            TechnicalIndicator.objects.create(
                pair=pair,
                exchange=exchange,
                indicator_type='EMA',
                timeframe='1h',  # Default timeframe
                value=ema_value,
                timestamp=timezone.now(),
                additional_data={
                    'period': 200,
                    'source': 'tradingview_webhook'
                }
            )

            # Update bot's EMA value if it has this capability
            if hasattr(quantum_bot, 'update_ema'):
                quantum_bot.update_ema(ema_value, pair)
                bot_updated = True
            else:
                bot_updated = False

            return {
                'bot_updated': bot_updated,
                'quantum_bot_id': str(quantum_bot.id),
                'message': 'EMA value stored and processed'
            }

        except Exception as e:
            logger.error(f"Error processing EMA signal: {e}")
            return {'bot_updated': False, 'message': str(e)}


@method_decorator(csrf_exempt, name='dispatch')
class RSIIndicatorView(View):
    """
    Webhook endpoint for RSI (Relative Strength Index) indicators.
    """

    def post(self, request):
        """Process RSI indicator signal."""
        try:
            # Parse request data
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            # Extract RSI data
            rsi_value = data.get('RSI')
            prev_rsi_value = data.get('PrevRSI')
            color = data.get('color')
            prev_color = data.get('prev_color')

            if rsi_value is None:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No RSI value found in request'
                }, status=status.HTTP_400_BAD_REQUEST)

            username = data.get('username')
            pair = data.get('pair')
            exchange = data.get('exchange', 'binance')

            # Process RSI signal
            result = self.process_rsi_signal(
                rsi_value, prev_rsi_value, color, prev_color,
                username, pair, exchange
            )

            return JsonResponse({
                'status': 'success',
                'message': f'RSI processed for {pair}',
                'rsi_value': rsi_value,
                'bot_updated': result['bot_updated']
            })

        except Exception as e:
            logger.error(f"RSI processing error: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'RSI processing failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def process_rsi_signal(self, rsi_value: float, prev_rsi_value: float = None,
                           color: str = None, prev_color: str = None,
                           username: str = None, pair: str = None,
                           exchange: str = None) -> dict:
        """Process RSI signal for Quantum AI bot."""
        try:
            from django.contrib.auth import get_user_model
            from apps.bots.models import QuantumAIBot, TechnicalIndicator

            User = get_user_model()

            # Get user
            user = User.objects.get(username=username)

            # Get Quantum AI bot
            quantum_bot = QuantumAIBot.objects.filter(
                user=user,
                is_active=True,
                is_deleted=False
            ).first()

            if not quantum_bot:
                return {'bot_updated': False, 'message': 'No active Quantum AI bot found'}

            # Store technical indicator
            TechnicalIndicator.objects.create(
                pair=pair,
                exchange=exchange,
                indicator_type='RSI',
                timeframe='1h',
                value=rsi_value,
                timestamp=timezone.now(),
                additional_data={
                    'prev_rsi': prev_rsi_value,
                    'color': color,
                    'prev_color': prev_color,
                    'source': 'tradingview_webhook'
                }
            )

            # Update bot's RSI value
            bot_updated = False
            if hasattr(quantum_bot, 'update_rsi'):
                quantum_bot.update_rsi(rsi_value, pair, {
                    'prev_rsi': prev_rsi_value,
                    'color': color,
                    'prev_color': prev_color
                })
                bot_updated = True

            return {
                'bot_updated': bot_updated,
                'quantum_bot_id': str(quantum_bot.id),
                'message': 'RSI value stored and processed'
            }

        except Exception as e:
            logger.error(f"Error processing RSI signal: {e}")
            return {'bot_updated': False, 'message': str(e)}