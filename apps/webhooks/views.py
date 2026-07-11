"""
Webhook views for TradingView and Technical Indicators
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.utils import timezone as _tz
from datetime import datetime, timedelta
import logging
import hmac as _hmac

logger = logging.getLogger(__name__)


def _parse_tv_timestamp(raw: str) -> datetime | None:
    """Parse TradingView timestamp — ISO 8601 ({{timenow}}) or Unix ms ({{time}}).

    Returns timezone-aware datetime in UTC, or None if unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip().strip('"').strip("'")
    # ISO 8601:  2026-06-21T12:34:56Z  or  2026-06-21T12:34:56.123Z
    try:
        if raw.endswith('Z'):
            raw_clean = raw[:-1]
            if '.' in raw_clean:
                dt = datetime.strptime(raw_clean, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                dt = datetime.strptime(raw_clean, '%Y-%m-%dT%H:%M:%S')
            return dt.replace(tzinfo=_tz.UTC)
    except ValueError:
        pass
    # Unix epoch milliseconds
    try:
        ms = int(raw)
        if 1_000_000_000_000 < ms < 2_000_000_000_000:  # sanity: 2001-2033
            return datetime.fromtimestamp(ms / 1000, tz=_tz.UTC)
    except (ValueError, TypeError):
        pass
    return None


def _webhook_fail_key(bot_id: str) -> str:
    return f"webhook:fail:{bot_id}"


def _webhook_dedupe_key(bot_id: str, ts: str, side: str, pair: str, pos_size: str) -> str:
    import hashlib
    raw = f"{bot_id}|{ts}|{side}|{pair}|{pos_size}"
    return f"webhook:dedupe:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


RATE_LIMIT_FAILURES = 5
RATE_LIMIT_WINDOW = 300  # 5 minutes
TIMESTAMP_MAX_AGE = 120  # seconds


@method_decorator(csrf_exempt, name='dispatch')
class SignalBotWebhookView(APIView):
    """
    Global webhook endpoint for Signal Bot (TradingView)
    URL: /api/webhooks/signalbot/
    Accepts bot_id and secret in JSON payload to identify bot and execute trades
    """
    permission_classes = [AllowAny]
    throttle_scope = 'webhook'

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
            
            safe_payload = {k: v for k, v in payload.items() if k != 'secret'}
            logger.info(f"Received webhook payload: {safe_payload}")

            # Validate required fields
            bot_id = payload.get('bot_id')
            secret = payload.get('secret')
            side = payload.get('side', '').lower()
            trading_pair = payload.get('Pair')

            if not bot_id:
                return Response({'error': 'Missing bot_id in payload'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not secret:
                return Response({'error': 'Missing secret in payload'}, status=status.HTTP_400_BAD_REQUEST)

            # Rate limit check: too many recent validation failures for this bot_id
            fail_count = cache.get(_webhook_fail_key(bot_id), 0)
            if fail_count >= RATE_LIMIT_FAILURES:
                logger.warning(f"Bot {bot_id} rate-limited ({fail_count} failures in {RATE_LIMIT_WINDOW}s)")
                return Response({'error': 'Too many failed attempts'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

            # Timestamp validation (replay window)
            ts_raw = payload.get('timestamp')
            if not ts_raw:
                _fails = cache.add(_webhook_fail_key(bot_id), 1, RATE_LIMIT_WINDOW)
                if not _fails:
                    cache.incr(_webhook_fail_key(bot_id), 1)
                logger.warning(f"Missing timestamp for bot {bot_id}")
                return Response({'error': 'Missing timestamp'}, status=status.HTTP_400_BAD_REQUEST)

            ts_dt = _parse_tv_timestamp(str(ts_raw))
            if ts_dt is None:
                _fails = cache.add(_webhook_fail_key(bot_id), 1, RATE_LIMIT_WINDOW)
                if not _fails:
                    cache.incr(_webhook_fail_key(bot_id), 1)
                    cache.touch(_webhook_fail_key(bot_id), RATE_LIMIT_WINDOW)
                logger.warning(f"Unparseable timestamp for bot {bot_id}: {ts_raw}")
                return Response({'error': 'Invalid timestamp'}, status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now()
            age = (now - ts_dt).total_seconds()
            if abs(age) > TIMESTAMP_MAX_AGE:
                _fails = cache.add(_webhook_fail_key(bot_id), 1, RATE_LIMIT_WINDOW)
                if not _fails:
                    cache.incr(_webhook_fail_key(bot_id), 1)
                    cache.touch(_webhook_fail_key(bot_id), RATE_LIMIT_WINDOW)
                logger.warning(f"Timestamp too old for bot {bot_id}: {age:.0f}s")
                return Response({'error': 'Timestamp expired'}, status=status.HTTP_400_BAD_REQUEST)

            # Find bot by bot_id and validate secret in constant time
            try:
                bot = SignalBot.objects.select_related('user', 'subscription').get(
                    bot_id=bot_id,
                    is_deleted=False,
                )
            except SignalBot.DoesNotExist:
                _fails = cache.add(_webhook_fail_key(bot_id), 1, RATE_LIMIT_WINDOW)
                if not _fails:
                    cache.incr(_webhook_fail_key(bot_id), 1)
                    cache.touch(_webhook_fail_key(bot_id), RATE_LIMIT_WINDOW)
                logger.warning(f"Invalid bot_id: {bot_id}")
                return Response({'error': 'Invalid bot_id or secret'}, status=status.HTTP_403_FORBIDDEN)

            import hmac as _hmac
            if not _hmac.compare_digest(str(secret), str(bot.secret_key or '')):
                _fails = cache.add(_webhook_fail_key(bot_id), 1, RATE_LIMIT_WINDOW)
                if not _fails:
                    cache.incr(_webhook_fail_key(bot_id), 1)
                    cache.touch(_webhook_fail_key(bot_id), RATE_LIMIT_WINDOW)
                logger.warning(f"Invalid secret for bot {bot_id}")
                return Response({'error': 'Invalid bot_id or secret'}, status=status.HTTP_403_FORBIDDEN)

            # Redis dedupe — reject exact replay within 120 s window
            dedupe_key = _webhook_dedupe_key(
                bot_id, ts_raw, side, trading_pair,
                str(payload.get('position_size', ''))
            )
            if not cache.add(dedupe_key, '1', TIMESTAMP_MAX_AGE):
                logger.info(f"Dedupe hit for {dedupe_key[:40]}… — ignoring replay")
                return Response({'success': True, 'message': 'Duplicate ignored'}, status=status.HTTP_200_OK)

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
            # SECURITY: never echo internal exception strings to clients —
            # they can include CCXT API error messages, credential fragments,
            # or DB schema details. ``exc_info`` removed here because local
            # frames carry decrypted ``api_key``/``secret_key`` variables
            # (see execute_trade above).
            logger.error(f"Webhook processing error: {type(e).__name__}")
            return Response({'error': 'Server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            # See note on the outer handler — do not include exc_info here:
            # ``api_key`` / ``secret_key`` / ``passphrase`` are local
            # variables of ``execute_trade`` and would be captured by the
            # traceback machinery.
            logger.error(f"Trade execution error: {type(e).__name__}")
            return {'status': 'error', 'message': 'Trade execution failed'}


@method_decorator(csrf_exempt, name='dispatch')
class TradingViewWebhookView(APIView):
    """
    Webhook endpoint for TradingView alerts
    """
    permission_classes = [AllowAny]
    throttle_scope = 'webhook'

    def post(self, request, webhook_id):
        """
        Handle incoming webhook from TradingView
        """
        try:
            # Log the incoming webhook
            logger.info(f"Received TradingView webhook: {webhook_id}")
            logger.debug(f"Webhook payload keys: {list(request.data.keys()) if request.data else 'empty'}")

            # TODO (CRIT-3): Implement webhook processing logic
            # 1. Validate webhook_id against WebhookAlertBot model
            # 2. Validate secret using hmac.compare_digest()
            # 3. Process the trading signal
            # 4. Execute trades based on alert

            return Response({
                'status': 'success',
                'message': 'Webhook received',
                'webhook_id': str(webhook_id)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # SECURITY (CRIT-3): NEVER echo str(e) to clients — it can
            # contain DB table names, field names, CCXT API error details,
            # and partial credential info.
            logger.error(f"Error processing webhook {webhook_id}: {type(e).__name__}")
            return Response({
                'status': 'error',
                'message': 'Webhook processing failed'
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
