"""
Webhook views for TradingView and Technical Indicators
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class SignalBotWebhookView(APIView):
    """
    Global webhook endpoint for Signal Bot (TradingView)
    URL: /api/webhooks/signalbot/
    Accepts bot_id and secret in JSON payload to identify bot and execute trades
    """
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Handle incoming webhook from TradingView and execute trade via CCXT
        Required payload fields: bot_id, secret, side, Pair
        Optional: position_size (if use_tradingView_position_size=True)
        """
        import ccxt
        import math
        from decimal import Decimal
        from apps.bots.models import SignalBot
        from apps.exchanges.models import ExchangeCredentials
        from django.utils import timezone

        try:
            # Parse payload (handle both JSON and string-wrapped JSON)
            raw_data = request.body.decode('utf-8').strip('"')
            if raw_data.startswith('{'):
                import json
                payload = json.loads(raw_data)
            else:
                payload = request.data
            
            logger.info(f"Received webhook payload: {payload}")

            # Validate required fields
            bot_id = payload.get('bot_id')
            secret = payload.get('secret')
            side = payload.get('side', '').lower()
            trading_pair = payload.get('Pair')

            if not bot_id:
                return Response({'error': 'Missing bot_id in payload'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not secret:
                return Response({'error': 'Missing secret in payload'}, status=status.HTTP_400_BAD_REQUEST)

            # Find bot by bot_id and validate secret
            try:
                bot = SignalBot.objects.select_related('user', 'subscription').get(
                    bot_id=bot_id,
                    secret_key=secret,
                    is_deleted=False
                )
            except SignalBot.DoesNotExist:
                logger.warning(f"Invalid bot_id or secret: {bot_id}")
                return Response({'error': 'Invalid bot_id or secret'}, status=status.HTTP_403_FORBIDDEN)

            user = bot.user

            # Validate bot is active
            if not bot.is_active:
                logger.info(f"Bot {bot_id} is not active")
                return Response({'error': 'Bot is not active'}, status=status.HTTP_403_FORBIDDEN)

            # Validate subscription is active
            if bot.subscription and bot.subscription.status != 'active':
                logger.info(f"Bot {bot_id} subscription is {bot.subscription.status}")
                return Response({'error': f'Subscription is {bot.subscription.status}'}, status=status.HTTP_403_FORBIDDEN)

            # Validate side
            if side not in ['buy', 'sell']:
                return Response({'error': 'Invalid side, must be buy or sell'}, status=status.HTTP_400_BAD_REQUEST)

            # Get trading pair
            if not trading_pair:
                trading_pair = bot.trading_pair
            
            if not trading_pair:
                return Response({'error': 'No trading pair specified'}, status=status.HTTP_400_BAD_REQUEST)

            # Determine position size
            position_size = None
            if bot.use_tradingView_position_size:
                position_size = payload.get('position_size')
                if not position_size:
                    return Response({'error': 'TradingView position size enabled but not provided'}, status=status.HTTP_400_BAD_REQUEST)
                
                try:
                    position_size = float(position_size)
                    if position_size < 0:
                        position_size = math.fabs(position_size)
                    if not position_size or position_size == 0:
                        position_size = float(bot.default_amount)
                except (ValueError, TypeError):
                    return Response({'error': 'Invalid position size format'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                position_size = float(bot.default_amount)

            # Execute the trade
            trade_result = self.execute_trade(
                user=user,
                bot=bot,
                exchange_name=bot.exchange_name,
                side=side,
                trading_pair=trading_pair,
                position_size=position_size
            )

            # Update bot statistics
            bot.last_triggered = timezone.now()
            bot.total_trades += 1
            bot.signals_used_this_month += 1
            bot.save()

            logger.info(f"Trade executed for bot {bot_id}: {side} {position_size} {trading_pair}")

            return Response({
                'success': True,
                'message': f'Trade executed: {side} {position_size} of {trading_pair}',
                'trade_details': trade_result
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
            return Response({'error': f'Server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def execute_trade(self, user, bot, exchange_name, side, trading_pair, position_size):
        """
        Execute trade using CCXT for the specified exchange
        Supports: Binance, Bybit, OKX, MEXC, and others
        """
        import ccxt
        from apps.exchanges.models import ExchangeCredentials
        
        try:
            # Get exchange credentials
            try:
                credentials = ExchangeCredentials.objects.get(
                    user=user,
                    exchange_name=exchange_name,
                    is_active=True
                )
            except ExchangeCredentials.DoesNotExist:
                raise ValueError(f"{exchange_name} API credentials not configured")

            # Get decrypted credentials
            creds = credentials.get_decrypted_credentials()
            api_key = creds['api_key']
            secret_key = creds['secret_key']
            passphrase = creds.get('passphrase')

            # Initialize CCXT exchange
            exchange_class = getattr(ccxt, exchange_name.lower(), None)
            if not exchange_class:
                raise ValueError(f"Exchange {exchange_name} not supported by CCXT")

            exchange_config = {
                'apiKey': api_key,
                'secret': secret_key,
                'enableRateLimit': True,
            }
            
            if passphrase:
                exchange_config['password'] = passphrase

            # Create exchange instance
            exchange_instance = exchange_class(exchange_config)

            # Load markets
            exchange_instance.load_markets()
            
            if trading_pair not in exchange_instance.markets:
                return {'status': 'error', 'message': f'Trading pair {trading_pair} not available on {exchange_name}'}

           # Get current price
            current_price = float(exchange_instance.fetch_ticker(trading_pair)['last'])
            
            # Convert position size to coins if not using TradingView position size
            if not bot.use_tradingView_position_size:
                # position_size is in USDT, convert to coins
                position_size = round(position_size / current_price, 8)

            # Execute market order
            order = exchange_instance.create_order(
                symbol=trading_pair,
                type='market',
                side=side,
                amount=position_size,
                price=current_price
            )

            logger.info(f"{side.upper()} order executed: {order}")

            return {
                'status': 'success',
                'order_id': order.get('id'),
                'timestamp': order.get('timestamp'),
                'amount': order.get('amount'),
                'price': order.get('price'),
                'cost': order.get('cost'),
                'exchange': exchange_name
            }

        except Exception as e:
            logger.error(f"Trade execution error: {str(e)}", exc_info=True)
            return {'status': 'error', 'message': str(e)}


@method_decorator(csrf_exempt, name='dispatch')
class TradingViewWebhookView(APIView):
    """
    Webhook endpoint for TradingView alerts
    """
    permission_classes = [AllowAny]

    def post(self, request, webhook_id):
        """
        Handle incoming webhook from TradingView
        """
        try:
            # Log the incoming webhook
            logger.info(f"Received TradingView webhook: {webhook_id}")
            logger.debug(f"Webhook payload: {request.data}")

            # TODO: Implement webhook processing logic
            # 1. Validate webhook_id
            # 2. Process the trading signal
            # 3. Execute trades based on alert

            return Response({
                'status': 'success',
                'message': 'Webhook received',
                'webhook_id': str(webhook_id)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing webhook {webhook_id}: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EMAIndicatorView(APIView):
    """
    View for calculating Exponential Moving Average (EMA) indicator
    """
    def get(self, request):
        """
        Calculate EMA indicator
        """
        try:
            # Get parameters from request
            symbol = request.query_params.get('symbol')
            period = int(request.query_params.get('period', 20))
            timeframe = request.query_params.get('timeframe', '1h')

            # TODO: Implement EMA calculation
            # 1. Fetch historical price data
            # 2. Calculate EMA
            # 3. Return result

            return Response({
                'indicator': 'EMA',
                'symbol': symbol,
                'period': period,
                'timeframe': timeframe,
                'value': None,  # Calculate actual value
                'message': 'EMA calculation not yet implemented'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error calculating EMA: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RSIIndicatorView(APIView):
    """
    View for calculating Relative Strength Index (RSI) indicator
    """
    def get(self, request):
        """
        Calculate RSI indicator
        """
        try:
            # Get parameters from request
            symbol = request.query_params.get('symbol')
            period = int(request.query_params.get('period', 14))
            timeframe = request.query_params.get('timeframe', '1h')

            # TODO: Implement RSI calculation
            # 1. Fetch historical price data
            # 2. Calculate RSI
            # 3. Return result

            return Response({
                'indicator': 'RSI',
                'symbol': symbol,
                'period': period,
                'timeframe': timeframe,
                'value': None,  # Calculate actual value
                'message': 'RSI calculation not yet implemented'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error calculating RSI: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
