"""
Technical indicator webhook views for async trading signals.
"""
import json
import logging
from django.views import View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Q
from asgiref.sync import sync_to_async

logger = logging.getLogger('apps.indicators')


@method_decorator(csrf_exempt, name='dispatch')
class EMAIndicatorView(View):
    """Handle EMA (Exponential Moving Average) webhook signals."""

    async def post(self, request):
        """Process EMA trading signal."""
        try:
            # Parse JSON data
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            # Validate required fields
            if "EMA200" not in data:
                return JsonResponse({
                    'status': 'error',
                    'message': 'EMA200 value is required'
                }, status=400)

            username = data.get("username")
            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "binance")
            ema_value = data.get("EMA200")

            if not username or not pair_symbol:
                return JsonResponse({
                    'status': 'error',
                    'message': 'username and pair are required'
                }, status=400)

            # Get user and pair config
            from apps.authentication.models import User
            from apps.bots.models import PairConfig

            try:
                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except User.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'User {username} not found'
                }, status=404)
            except PairConfig.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Pair config for {pair_symbol} not found'
                }, status=404)

            # Update bot configuration
            bot = await self.get_or_create_bot(user, pair_config, exchange)
            bot.EMA = ema_value
            await sync_to_async(bot.save)()

            # Check entry conditions
            await self.check_entry_conditions(bot, data)

            return JsonResponse({
                'status': 'success',
                'message': f'EMA processed for {pair_symbol}',
                'EMA': ema_value,
                'bot_updated': True
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        except Exception as e:
            logger.error(f"Error in EMA webhook: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error'
            }, status=500)

    async def get_or_create_bot(self, user, pair_config, exchange):
        """Get or create Quantum AI bot for the user."""
        from apps.bots.models import QuantumAIBot

        bot, created = await sync_to_async(QuantumAIBot.objects.get_or_create)(
            user=user,
            defaults={
                'bot_name': f'{pair_config.pair_symbol} Quantum AI',
                'is_active': True
            }
        )
        return bot

    async def check_entry_conditions(self, bot, data):
        """Check if entry conditions are met based on EMA signals."""
        ema_value = float(data.get("EMA200", 0))

        # Simple EMA-based entry logic
        if ema_value > 0:
            # Update bot's technical indicators
            bot_details = {
                'ema_value': ema_value,
                'timestamp': data.get('timestamp'),
                'signal_strength': 'medium'
            }

            # Log the signal
            await self.log_signal(bot, 'EMA', bot_details)

    async def log_signal(self, bot, indicator_type, details):
        """Log technical indicator signal."""
        from apps.bots.models import BotExecutionLog

        await sync_to_async(BotExecutionLog.objects.create)(
            user=bot.user,
            bot_type='quantum',
            bot_id=bot.id,
            action=f'{indicator_type}_signal',
            message=f'{indicator_type} signal received: {details}',
            level='info',
            data=details
        )


@method_decorator(csrf_exempt, name='dispatch')
class RSIIndicatorView(View):
    """Handle RSI (Relative Strength Index) webhook signals."""

    async def post(self, request):
        """Process RSI trading signal."""
        try:
            # Parse JSON data
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            # Validate required fields
            if "RSI" not in data:
                return JsonResponse({
                    'status': 'error',
                    'message': 'RSI value is required'
                }, status=400)

            username = data.get("username")
            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "binance")
            rsi_value = data.get("RSI")
            prev_rsi = data.get("PrevRSI", rsi_value)
            color = data.get("color", "white")
            prev_color = data.get("prev_color", "white")

            if not username or not pair_symbol:
                return JsonResponse({
                    'status': 'error',
                    'message': 'username and pair are required'
                }, status=400)

            # Get user and pair config
            from apps.authentication.models import User
            from apps.bots.models import PairConfig

            try:
                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except User.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'User {username} not found'
                }, status=404)
            except PairConfig.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Pair config for {pair_symbol} not found'
                }, status=404)

            # Update bot configuration
            bot = await self.get_or_create_bot(user, pair_config, exchange)
            bot.RSI = rsi_value
            await sync_to_async(bot.save)()

            # Check entry conditions
            await self.check_entry_conditions(bot, data)

            return JsonResponse({
                'status': 'success',
                'message': f'RSI processed for {pair_symbol}',
                'RSI': rsi_value,
                'bot_updated': True
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        except Exception as e:
            logger.error(f"Error in RSI webhook: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error'
            }, status=500)

    async def get_or_create_bot(self, user, pair_config, exchange):
        """Get or create Quantum AI bot for the user."""
        from apps.bots.models import QuantumAIBot

        bot, created = await sync_to_async(QuantumAIBot.objects.get_or_create)(
            user=user,
            defaults={
                'bot_name': f'{pair_config.pair_symbol} Quantum AI',
                'is_active': True
            }
        )
        return bot

    async def check_entry_conditions(self, bot, data):
        """Check if entry conditions are met based on RSI signals."""
        rsi_value = float(data.get("RSI", 50))
        prev_rsi = float(data.get("PrevRSI", 50))
        color = data.get("color", "white")
        prev_color = data.get("prev_color", "white")

        # RSI-based entry logic
        signal_type = None
        if rsi_value < 30 and prev_rsi >= 30:  # Oversold crossover
            signal_type = 'buy'
        elif rsi_value > 70 and prev_rsi <= 70:  # Overbought crossover
            signal_type = 'sell'

        if signal_type:
            bot_details = {
                'rsi_value': rsi_value,
                'prev_rsi': prev_rsi,
                'signal_type': signal_type,
                'color': color,
                'prev_color': prev_color,
                'timestamp': data.get('timestamp')
            }

            # Log the signal
            await self.log_signal(bot, 'RSI', bot_details)

    async def log_signal(self, bot, indicator_type, details):
        """Log technical indicator signal."""
        from apps.bots.models import BotExecutionLog

        await sync_to_async(BotExecutionLog.objects.create)(
            user=bot.user,
            bot_type='quantum',
            bot_id=bot.id,
            action=f'{indicator_type}_signal',
            message=f'{indicator_type} signal received: {details}',
            level='info',
            data=details
        )


@method_decorator(csrf_exempt, name='dispatch')
class BollingerBandsView(View):
    """Handle Bollinger Bands webhook signals."""

    async def post(self, request):
        """Process Bollinger Bands trading signal."""
        try:
            # Parse JSON data
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            # Validate required fields
            if "BB" not in data:
                return JsonResponse({
                    'status': 'error',
                    'message': 'BB value is required'
                }, status=400)

            username = data.get("username")
            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "binance")
            bb_signal = data.get("BB")

            if not username or not pair_symbol:
                return JsonResponse({
                    'status': 'error',
                    'message': 'username and pair are required'
                }, status=400)

            # Get user and pair config
            from apps.authentication.models import User
            from apps.bots.models import PairConfig

            try:
                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except User.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'User {username} not found'
                }, status=404)
            except PairConfig.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Pair config for {pair_symbol} not found'
                }, status=404)

            # Update bot configuration
            bot = await self.get_or_create_bot(user, pair_config, exchange)
            bot.BB = bb_signal
            await sync_to_async(bot.save)()

            # Check entry conditions
            await self.check_entry_conditions(bot, data)

            return JsonResponse({
                'status': 'success',
                'message': f'Bollinger Bands processed for {pair_symbol}',
                'BB': bb_signal,
                'bot_updated': True
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        except Exception as e:
            logger.error(f"Error in Bollinger Bands webhook: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error'
            }, status=500)

    async def get_or_create_bot(self, user, pair_config, exchange):
        """Get or create Quantum AI bot for the user."""
        from apps.bots.models import QuantumAIBot

        bot, created = await sync_to_async(QuantumAIBot.objects.get_or_create)(
            user=user,
            defaults={
                'bot_name': f'{pair_config.pair_symbol} Quantum AI',
                'is_active': True
            }
        )
        return bot

    async def check_entry_conditions(self, bot, data):
        """Check if entry conditions are met based on Bollinger Bands signals."""
        bb_signal = data.get("BB", "")

        # Bollinger Bands-based entry logic
        signal_type = None
        if "Crossing Up Band" in bb_signal:
            signal_type = 'buy'
        elif "Crossing Down Band" in bb_signal:
            signal_type = 'sell'

        if signal_type:
            bot_details = {
                'bb_signal': bb_signal,
                'signal_type': signal_type,
                'timestamp': data.get('timestamp')
            }

            # Log the signal
            await self.log_signal(bot, 'BollingerBands', bot_details)

    async def log_signal(self, bot, indicator_type, details):
        """Log technical indicator signal."""
        from apps.bots.models import BotExecutionLog

        await sync_to_async(BotExecutionLog.objects.create)(
            user=bot.user,
            bot_type='quantum',
            bot_id=bot.id,
            action=f'{indicator_type}_signal',
            message=f'{indicator_type} signal received: {details}',
            level='info',
            data=details
        )