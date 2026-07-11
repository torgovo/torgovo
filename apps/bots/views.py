"""
Views for bot management endpoints.

All bot CRUD operations, start/stop controls, and admin indicator views.
Separated from apps/payments/views.py for clean concern separation.
"""
import json
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.template.response import TemplateResponse
from asgiref.sync import sync_to_async
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from apps.bots.models import (
    SignalBot, GridBot, MartingaleBot,
    QuantumAIFund, QuantumAIInvestment,
    PairConfig, Order, Indicator,
    TelegramSignalSubscription, TelegramSignalPlan
)
from apps.bots.serializers import (
    SignalBotSerializer, SignalBotCreateSerializer,
    GridBotSerializer, GridBotCreateSerializer,
    MartingaleBotSerializer, MartingaleBotCreateSerializer,
    QuantumAIFundSerializer, QuantumAIInvestmentSerializer,
    PairConfigSerializer, OrderSerializer, IndicatorSerializer,
    TelegramSignalSubscriptionSerializer, TelegramSignalPlanSerializer
)
from apps.payments.models import BotSubscription

logger = logging.getLogger('bots')


def _resolve_webhook_user(request):
    """Resolve user from X-Webhook-Token header. Returns user or None."""
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    User = get_user_model()
    token = request.headers.get('X-Webhook-Token') or request.POST.get('webhook_token')
    if not token:
        return None
    try:
        return User.objects.get(webhook_token=token)
    except (User.DoesNotExist, ValidationError):
        return None


# ==================== SIGNAL BOT (TradingView Webhook) ====================

class SignalBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Signal Bots (TradingView webhook bots).
    Users create a signal bot, get a webhook URL, and connect it to TradingView.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return SignalBot.objects.all()
        return SignalBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return SignalBotCreateSerializer
        return SignalBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='custom',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Signal Bot subscription")

        bot = serializer.save(user=self.request.user, subscription=subscription)
        bot.generate_webhook_credentials()

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle bot active/inactive status"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        bot.is_active = not bot.is_active
        bot.save()

        return Response({
            'success': True,
            'is_active': bot.is_active,
            'message': f'Bot {bot.bot_name} is now {"active" if bot.is_active else "inactive"}'
        })


# ==================== GRID BOT ====================

class GridBotViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Grid Trading bots"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return GridBot.objects.all()
        return GridBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return GridBotCreateSerializer
        return GridBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='grid',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Grid Bot subscription")

        existing_bot = GridBot.objects.filter(
            subscription=subscription,
            is_deleted=False
        ).first()

        if existing_bot:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You already have a Grid Bot for this subscription. "
                "You can update the existing bot's settings instead."
            )

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start the grid bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if not bot.subscription or bot.subscription.status != 'active':
            return Response({'error': 'No active subscription'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # TODO: Integrate with BotExecutor service
            bot.is_running = True
            bot.started_at = timezone.now()
            bot.save()
            return Response({'success': True, 'message': 'Grid bot started'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop the grid bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        try:
            # TODO: Integrate with BotExecutor service
            bot.is_running = False
            bot.stopped_at = timezone.now()
            bot.save()
            return Response({'success': True, 'message': 'Grid bot stopped'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MARTINGALE BOT ====================

class MartingaleBotViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Martingale bots"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return MartingaleBot.objects.all()
        return MartingaleBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return MartingaleBotCreateSerializer
        return MartingaleBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='martingale',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Martingale Bot subscription")

        existing_bot = MartingaleBot.objects.filter(
            subscription=subscription,
            is_deleted=False
        ).first()

        if existing_bot:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You already have a Martingale Bot for this subscription. "
                "You can update the existing bot's settings instead."
            )

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start the martingale bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if not bot.subscription or bot.subscription.status != 'active':
            return Response({'error': 'No active subscription'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # TODO: Integrate with BotExecutor service
            bot.is_running = True
            bot.started_at = timezone.now()
            bot.save()
            return Response({'success': True, 'message': 'Martingale bot started'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop the martingale bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        try:
            # TODO: Integrate with BotExecutor service
            bot.is_running = False
            bot.stopped_at = timezone.now()
            bot.save()
            return Response({'success': True, 'message': 'Martingale bot stopped'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== QUANTUM AI ====================

class QuantumAIFundViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Quantum AI Fund (Admin only)"""
    permission_classes = [IsAdminUser]
    queryset = QuantumAIFund.objects.all()
    serializer_class = QuantumAIFundSerializer


class QuantumAIInvestmentViewSet(viewsets.ModelViewSet):
    """ViewSet for user's Quantum AI investments"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return QuantumAIInvestment.objects.all()
        return QuantumAIInvestment.objects.filter(user=self.request.user)

    serializer_class = QuantumAIInvestmentSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='quantum_ai',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Quantum AI subscription")

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get user's current Quantum AI balance"""
        investments = self.get_queryset().filter(status='active')
        total_invested = sum(inv.amount for inv in investments)
        total_profit = sum(inv.accrued_profit for inv in investments)
        return Response({
            'total_invested': str(total_invested),
            'total_profit': str(total_profit),
            'current_balance': str(total_invested + total_profit),
        })


# ==================== PAIR CONFIG ====================

class PairConfigViewSet(viewsets.ModelViewSet):
    """ViewSet for PairConfig"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return PairConfig.objects.all()
        return PairConfig.objects.filter(user=self.request.user)

    serializer_class = PairConfigSerializer

    def perform_create(self, serializer):
        bot_type = serializer.validated_data.get('bot_type', 'grid')
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type=bot_type,
            status='active'
        ).first()

        if not subscription:
            raise PermissionError(f"No active subscription for {bot_type} bot")

        serializer.save(user=self.request.user, subscription=subscription)


# ==================== INDICATOR ====================

class IndicatorViewSet(viewsets.ModelViewSet):
    """ViewSet for technical indicators"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Indicator.objects.all()
        return Indicator.objects.filter(user=self.request.user)

    serializer_class = IndicatorSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ==================== ORDER ====================

class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for orders (read-only history)"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(user=self.request.user)

    serializer_class = OrderSerializer

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent orders"""
        recent_orders = self.get_queryset().select_related(
            'signal_bot', 'grid_bot', 'martingale_bot', 'quantum_ai_investment'
        )[:50]
        serializer = self.get_serializer(recent_orders, many=True)
        return Response(serializer.data)


# ==================== TELEGRAM SIGNALS ====================

class TelegramSignalPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Telegram signal plans (read-only)"""
    permission_classes = [IsAuthenticated]
    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer


class TelegramSignalSubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for Telegram signal subscriptions"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return TelegramSignalSubscription.objects.all()
        return TelegramSignalSubscription.objects.filter(user=self.request.user)

    serializer_class = TelegramSignalSubscriptionSerializer

    def perform_create(self, serializer):
        plan = serializer.validated_data.get('plan')
        expires_at = timezone.now() + timezone.timedelta(days=plan.duration_days) if plan else timezone.now() + timezone.timedelta(days=30)
        serializer.save(user=self.request.user, expires_at=expires_at)


# ==================== ADMIN INDICATOR VIEWS (Old Code) ====================

@method_decorator(csrf_exempt, name='dispatch')
class IndicatorView(View):
    """Old endpoint for Binance indicators - admin only"""

    async def get(self, request, username, pair):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user, slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, 'binance')

            context = {
                'Pair': getattr(bot, 'symbol', pair),
                'username': username,
                'pair': pair,
                'Reason': getattr(bot, 'reason', ''),
                'Prev_Reason': getattr(bot, 'PrevReason', ''),
                'Percentage': getattr(bot, 'Percentage', 0),
                'UnrealizedPnl': getattr(bot, 'Unrealized_Pnl', 0),
                'Current_Price': getattr(bot, 'current_price', 0),
                'EMA': getattr(bot, 'EMA', 0),
                'RSI': getattr(bot, 'RSI', 0),
                'PrevRSI': getattr(bot, 'PrevRSI', 0),
                'RSI_color': getattr(bot, 'RSI_color', ''),
                'RSI_prev_color': getattr(bot, 'RSI_prev_color', ''),
                'BB': getattr(bot, 'BB', ''),
                'count': getattr(bot, 'count', 0),
                'current_side': getattr(bot, 'current_side', 'N/A'),
                'bot_running': getattr(bot, 'monitoring', False),
                'favor_levels': getattr(bot, 'favor_lvl', []),
                'against_levels': getattr(bot, 'against_lvl', []),
            }
            return TemplateResponse(request, 'indicators.html', context)

        except Exception as e:
            logger.error(f"Error in Indicator view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BybitIndicatorView(View):
    """Old endpoint for Bybit indicators - admin only"""

    async def get(self, request, username, pair):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user, slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, 'bybit')

            context = {
                'Pair': getattr(bot, 'symbol', pair),
                'username': username,
                'pair': pair,
                'Reason': getattr(bot, 'reason', ''),
                'Prev_Reason': getattr(bot, 'PrevReason', ''),
                'Percentage': getattr(bot, 'Percentage', 0),
                'UnrealizedPnl': getattr(bot, 'Unrealized_Pnl', 0),
                'last_trade_pnl': getattr(bot, 'last_trade_pnl', 0),
                'Current_Price': getattr(bot, 'current_price', 0),
                'EMA': getattr(bot, 'EMA', 0),
                'RSI': getattr(bot, 'RSI', 0),
                'PrevRSI': getattr(bot, 'PrevRSI', 0),
                'RSI_color': getattr(bot, 'RSI_color', ''),
                'RSI_prev_color': getattr(bot, 'RSI_prev_color', ''),
                'BB': getattr(bot, 'BB', ''),
                'count': getattr(bot, 'count', 0),
                'bot_running': getattr(bot, 'monitoring', False),
                'favor_levels': getattr(bot, 'favor_lvl', []),
                'against_levels': getattr(bot, 'against_lvl', []),
                'favor_length': len(getattr(bot, 'favor_lvl', [])),
                'against_length': len(getattr(bot, 'against_lvl', [])),
            }
            return TemplateResponse(request, 'indicators.html', context)

        except Exception as e:
            logger.error(f"Error in BybitIndicator view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


class CustomOrderClosingView(View):
    """Manual order close endpoint - admin only (POST required for CSRF protection)"""

    async def post(self, request, username, pair):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user, slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, user.exchange or 'binance')

            if hasattr(bot, 'close_custom_order'):
                await bot.close_custom_order()

            return JsonResponse({"message": "Order Closed"}, status=200)

        except Exception as e:
            logger.error(f"Error closing order: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


class CustomOrderOpeningView(View):
    """Manual order open endpoint - admin only (POST required for CSRF protection)"""

    async def post(self, request, username, pair, side):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user, slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, user.exchange or 'binance')

            if hasattr(bot, 'buy_order') and side.lower() == 'buy':
                await bot.buy_order()
            elif hasattr(bot, 'sell_order') and side.lower() == 'sell':
                await bot.sell_order()

            return JsonResponse({"message": "Order Opened"}, status=200)

        except Exception as e:
            logger.error(f"Error opening order: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceEMAView(View):
    """Webhook endpoint for EMA updates"""

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"error": "Unauthorized"}, status=401)

            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "EMA200" in data:
                pair_symbol = data["pair"]
                exchange = data.get("exchange", "binance")
                ema_value = data["EMA200"]

                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config).data

                engine = await sync_to_async(get_or_create_engine)(
                    user, pair_config_dict, exchange,
                )
                if engine is None:
                    return JsonResponse({"error": "No exchange credentials"}, status=404)

                if hasattr(engine, 'update_conditions'):
                    engine.EMA = ema_value
                    engine.pair_config = pair_config_dict
                    await sync_to_async(engine.update_conditions)()

                return JsonResponse({
                    'status': 'success',
                    'message': f'EMA updated for {pair_symbol}',
                    'EMA': ema_value,
                })

            return JsonResponse({"message": "No EMA data"})

        except PairConfig.DoesNotExist:
            return JsonResponse({"error": "Pair config not found"}, status=404)
        except Exception as e:
            logger.error(f"Error in BinanceEMA view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceRSIView(View):
    """Webhook endpoint for RSI updates"""

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"error": "Unauthorized"}, status=401)

            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "RSI" in data:
                pair_symbol = data["pair"]
                exchange = data["exchange"]
                rsi_value = data["RSI"]
                PrevRSI = data.get('PrevRSI', 0)
                RSI_color = data.get('color', '')
                RSI_prev_color = data.get('prev_color', '')

                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config).data

                engine = await sync_to_async(get_or_create_engine)(
                    user, pair_config_dict, exchange,
                )
                if engine is None:
                    return JsonResponse({"error": "No exchange credentials"}, status=404)

                if hasattr(engine, 'update_conditions'):
                    engine.RSI = rsi_value
                    engine.PrevRSI = PrevRSI
                    engine.RSI_color = RSI_color
                    engine.RSI_prev_color = RSI_prev_color
                    engine.pair_config = pair_config_dict
                    await sync_to_async(engine.update_conditions)()

                return JsonResponse({
                    'status': 'success',
                    'message': f'RSI updated for {pair_symbol}',
                    'RSI': rsi_value,
                })

            return JsonResponse({"message": "No RSI data"})

        except PairConfig.DoesNotExist:
            return JsonResponse({"error": "Pair config not found"}, status=404)
        except Exception as e:
            logger.error(f"Error in BinanceRSI view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceBBView(View):
    """Webhook endpoint for BB updates"""

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"error": "Unauthorized"}, status=401)

            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "BB" in data:
                pair_symbol = data["pair"]
                exchange = data["exchange"]
                bb_value = data["BB"]

                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config).data

                engine = await sync_to_async(get_or_create_engine)(
                    user, pair_config_dict, exchange,
                )
                if engine is None:
                    return JsonResponse({"error": "No exchange credentials"}, status=404)

                if hasattr(engine, 'update_conditions'):
                    engine.BB = bb_value
                    engine.pair_config = pair_config_dict
                    await sync_to_async(engine.update_conditions)()

                return JsonResponse({
                    'status': 'success',
                    'message': f'BB updated for {pair_symbol}',
                    'BB': bb_value,
                })

            return JsonResponse({"message": "No BB data"})

        except PairConfig.DoesNotExist:
            return JsonResponse({"error": "Pair config not found"}, status=404)
        except Exception as e:
            logger.error(f"Error in BinanceBB view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


# ==================== HELPER FUNCTIONS ====================

def get_or_create_engine(user, pair_config_data, exchange_name):
    """
    Build a BotEngine config dict from user's PairConfig and credentials,
    then create a BotEngine instance.

    Replaces old trading_manager.get_bot / create_bot / start_bot pattern.
    """
    from apps.trading.engines.bot_engine import BotEngine
    from apps.exchanges.models import ExchangeCredentials
    from core.utils import decrypt_api_key

    pair_symbol = pair_config_data.get('pair_symbol', '')

    # Get user's exchange credentials
    try:
        credentials = ExchangeCredentials.objects.get(
            user=user, exchange_name=exchange_name, is_active=True
        )
        creds = credentials.get_decrypted_credentials()
    except ExchangeCredentials.DoesNotExist:
        logger.error(f"No credentials for {user.username} on {exchange_name}")
        return None

    config = {
        'bot_name': f"{user.username}_{pair_symbol}_{exchange_name}",
        'user_id': str(user.id),
        'strategy': 'quantum_ai',
        'symbol': pair_symbol,
        'exchange_name': exchange_name,
        'api_key': creds.get('api_key', ''),
        'secret_key': creds.get('secret_key', ''),
        'passphrase': creds.get('passphrase', ''),
        'is_testnet': getattr(credentials, 'is_testnet', False),
        'parameters': pair_config_data,
    }

    engine = BotEngine(config)
    return engine