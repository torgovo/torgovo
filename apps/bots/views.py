"""
Views for trading bot management
"""
import logging
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView

from .models import WebhookAlert, GridBot, MartingaleBot, QuantumAIBot
from .serializers import (
    WebhookAlertSerializer, WebhookAlertCreateSerializer,
    GridBotSerializer, GridBotCreateSerializer,
    MartingaleBotSerializer, MartingaleBotCreateSerializer,
    QuantumAIBotSerializer, QuantumAIBotCreateSerializer,
    OrderSerializer, TechnicalIndicatorSerializer,
    BotOverviewSerializer
)
from core.permissions import IsOwnerOrAdmin, IsAdminUser, CanCreateBots
from core.pagination import StandardResultsSetPagination

logger = logging.getLogger('apps.bots')


class WebhookAlertViewSet(generics.ModelViewSet):
    """ViewSet for WebhookAlert management."""
    queryset = WebhookAlert.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange_name', 'trading_pair', 'is_active']

    def get_queryset(self):
        """Filter by current user."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return WebhookAlertCreateSerializer
        return WebhookAlertSerializer


class GridBotViewSet(generics.ModelViewSet):
    """ViewSet for GridBot management."""
    queryset = GridBot.objects.all()
    permission_classes = [permissions.IsAuthenticated, CanCreateBots]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange_name', 'trading_pair', 'is_running']

    def get_queryset(self):
        """Filter by current user."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return GridBotCreateSerializer
        return GridBotSerializer


class MartingaleBotViewSet(generics.ModelViewSet):
    """ViewSet for MartingaleBot management."""
    queryset = MartingaleBot.objects.all()
    permission_classes = [permissions.IsAuthenticated, CanCreateBots]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange_name', 'trading_pair', 'is_running']

    def get_queryset(self):
        """Filter by current user."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return MartingaleBotCreateSerializer
        return MartingaleBotSerializer


class QuantumAIBotViewSet(generics.ModelViewSet):
    """ViewSet for QuantumAIBot management."""
    queryset = QuantumAIBot.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'risk_level', 'auto_compound']

    def get_queryset(self):
        """Filter by current user."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return QuantumAIBotCreateSerializer
        return QuantumAIBotSerializer


class OrderViewSet(generics.ModelViewSet):
    """ViewSet for Order history."""
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user', 'pair', 'exchange', 'category', 'side', 'status']

    def get_queryset(self):
        """Filter by current user."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset.select_related(
            'user', 'webhook_alert', 'grid_bot', 'martingale_bot', 'quantum_bot'
        ).order_by('-Time')


class TechnicalIndicatorViewSet(generics.ModelViewSet):
    """ViewSet for TechnicalIndicator data."""
    queryset = TechnicalIndicator.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['pair', 'exchange', 'indicator_type', 'timeframe']

    def get_queryset(self):
        """Get recent technical indicators."""
        queryset = super().get_queryset()
        return queryset.filter(
            timestamp__gte=timezone.now() - timezone.timedelta(days=30)
        ).order_by('-timestamp')


# Bot control endpoints
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_grid_bot(request, bot_id):
    """Start a grid bot."""
    try:
        bot = GridBot.objects.get(id=bot_id, user=request.user)

        if bot.is_running:
            return Response({
                'error': 'Bot is already running',
                'code': 'BOT_ALREADY_RUNNING'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Start the bot using trading manager
        from trading.manager import trading_manager

        config = {
            'trading_pair': bot.trading_pair,
            'base_amount': bot.base_amount,
            'favor_levels': bot.favor_levels,
            'against_levels': bot.against_levels,
            'level_spacing_percent': bot.level_spacing_percent,
            'take_profit_percent': bot.take_profit_percent,
            'stop_loss_percent': bot.stop_loss_percent
        }

        success = trading_manager.start_bot(request.user, 'grid', config)

        if success:
            bot.is_running = True
            bot.started_at = timezone.now()
            bot.save()

            return Response({
                'message': 'Grid bot started successfully',
                'bot_id': str(bot_id),
                'status': 'running'
            })
        else:
            return Response({
                'error': 'Failed to start bot',
                'code': 'BOT_START_FAILED'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except GridBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def stop_grid_bot(request, bot_id):
    """Stop a grid bot."""
    try:
        bot = GridBot.objects.get(id=bot_id, user=request.user)

        if not bot.is_running:
            return Response({
                'error': 'Bot is not running',
                'code': 'BOT_NOT_RUNNING'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Stop the bot using trading manager
        from trading.manager import trading_manager

        config = {
            'trading_pair': bot.trading_pair,
            'base_amount': bot.base_amount,
            'favor_levels': bot.favor_levels,
            'against_levels': bot.against_levels,
            'level_spacing_percent': bot.level_spacing_percent,
            'take_profit_percent': bot.take_profit_percent,
            'stop_loss_percent': bot.stop_loss_percent
        }

        success = trading_manager.stop_bot(request.user, 'grid', config)

        if success:
            bot.is_running = False
            bot.stopped_at = timezone.now()
            bot.save()

            return Response({
                'message': 'Grid bot stopped successfully',
                'bot_id': str(bot_id),
                'status': 'stopped',
                'final_profit_loss': float(bot.current_profit_loss)
            })
        else:
            return Response({
                'error': 'Failed to stop bot',
                'code': 'BOT_STOP_FAILED'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except GridBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Similar endpoints for martingale and quantum AI bots
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_martingale_bot(request, bot_id):
    """Start a martingale bot."""
    try:
        bot = MartingaleBot.objects.get(id=bot_id, user=request.user)

        if bot.is_running:
            return Response({
                'error': 'Bot is already running',
                'code': 'BOT_ALREADY_RUNNING'
            }, status=status.HTTP_400_BAD_REQUEST)

        from trading.manager import trading_manager

        config = {
            'trading_pair': bot.trading_pair,
            'base_amount': bot.base_amount,
            'favor_levels': bot.favor_levels,
            'against_levels': bot.against_levels,
            'level_spacing_percent': bot.level_spacing_percent,
            'multiplier_factor': bot.multiplier_factor,
            'take_profit_percent': bot.take_profit_percent,
            'stop_loss_percent': bot.stop_loss_percent
        }

        success = trading_manager.start_bot(request.user, 'martingale', config)

        if success:
            bot.is_running = True
            bot.started_at = timezone.now()
            bot.save()

            return Response({
                'message': 'Martingale bot started successfully',
                'bot_id': str(bot_id),
                'status': 'running'
            })

    except MartingaleBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def stop_martingale_bot(request, bot_id):
    """Stop a martingale bot."""
    try:
        bot = MartingaleBot.objects.get(id=bot_id, user=request.user)

        if not bot.is_running:
            return Response({
                'error': 'Bot is not running',
                'code': 'BOT_NOT_RUNNING'
            }, status=status.HTTP_400_BAD_REQUEST)

        from trading.manager import trading_manager

        config = {
            'trading_pair': bot.trading_pair,
            'base_amount': bot.base_amount,
            'favor_levels': bot.favor_levels,
            'against_levels': bot.against_levels,
            'level_spacing_percent': bot.level_spacing_percent,
            'multiplier_factor': bot.multiplier_factor,
            'take_profit_percent': bot.take_profit_percent,
            'stop_loss_percent': bot.stop_loss_percent
        }

        success = trading_manager.stop_bot(request.user, 'martingale', config)

        if success:
            bot.is_running = False
            bot.stopped_at = timezone.now()
            bot.save()

            return Response({
                'message': 'Martingale bot stopped successfully',
                'bot_id': str(bot_id),
                'status': 'stopped',
                'final_profit_loss': float(bot.current_profit_loss)
            })

    except MartingaleBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_quantum_ai_bot(request, bot_id):
    """Start a Quantum AI bot."""
    try:
        bot = QuantumAIBot.objects.get(id=bot_id, user=request.user)

        if bot.is_active:
            return Response({
                'error': 'Bot is already active',
                'code': 'BOT_ALREADY_ACTIVE'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Activate the bot
        bot.is_active = True
        bot.save()

        return Response({
            'message': 'Quantum AI bot activated successfully',
            'bot_id': str(bot_id),
            'status': 'active'
        })

    except QuantumAIBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def stop_quantum_ai_bot(request, bot_id):
    """Stop a Quantum AI bot."""
    try:
        bot = QuantumAIBot.objects.get(id=bot_id, user=request.user)

        if not bot.is_active:
            return Response({
                'error': 'Bot is not active',
                'code': 'BOT_NOT_ACTIVE'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Deactivate the bot
        bot.is_active = False
        bot.save()

        return Response({
            'message': 'Quantum AI bot deactivated successfully',
            'bot_id': str(bot_id),
            'status': 'inactive'
        })

    except QuantumAIBot.DoesNotExist:
        return Response({
            'error': 'Bot not found',
            'code': 'BOT_NOT_FOUND'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e),
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def bots_overview(request):
    """Get overview of user's bots."""
    try:
        user = request.user

        # Count bots by type
        webhook_count = WebhookAlert.objects.filter(user=user, is_deleted=False).count()
        grid_count = GridBot.objects.filter(user=user, is_deleted=False).count()
        martingale_count = MartingaleBot.objects.filter(user=user, is_deleted=False).count()
        quantum_count = QuantumAIBot.objects.filter(user=user, is_deleted=False).count()

        # Count running bots
        running_webhooks = WebhookAlert.objects.filter(user=user, is_active=True, is_deleted=False).count()
        running_grids = GridBot.objects.filter(user=user, is_running=True, is_deleted=False).count()
        running_martingales = MartingaleBot.objects.filter(user=user, is_running=True, is_deleted=False).count()
        active_quantum = QuantumAIBot.objects.filter(user=user, is_active=True, is_deleted=False).count()

        # Calculate total P&L
        from apps.bots.models import Order

        user_orders = Order.objects.filter(user=user)
        total_pnl = user_orders.aggregate(
            total=Sum('profit_loss')
        )['total'] or 0

        return Response({
            'user_bots': {
                'total': webhook_count + grid_count + martingale_count + quantum_count,
                'running': running_webhooks + running_grids + running_martingales + active_quantum,
                'webhook_alerts': {
                    'total': webhook_count,
                    'active': running_webhooks
                },
                'grid_bots': {
                    'total': grid_count,
                    'running': running_grids
                },
                'martingale_bots': {
                    'total': martingale_count,
                    'running': running_martingales
                },
                'quantum_ai': {
                    'total': quantum_count,
                    'active': active_quantum
                }
            },
            'performance': {
                'total_profit_loss': float(total_pnl),
                'total_trades': user_orders.count(),
                'total_orders': user_orders.count()
            }
        })

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def bot_performance(request, bot_id):
    """Get detailed performance statistics for a specific bot."""
    try:
        user = request.user

        # Try to find bot in any bot table
        bot = None
        bot_type = None

        if WebhookAlert.objects.filter(id=bot_id, user=user).exists():
            bot = WebhookAlert.objects.get(id=bot_id)
            bot_type = 'webhook'
        elif GridBot.objects.filter(id=bot_id, user=user).exists():
            bot = GridBot.objects.get(id=bot_id)
            bot_type = 'grid'
        elif MartingaleBot.objects.filter(id=bot_id, user=user).exists():
            bot = MartingaleBot.objects.get(id=bot_id)
            bot_type = 'martingale'
        elif QuantumAIBot.objects.filter(id=bot_id, user=user).exists():
            bot = QuantumAIBot.objects.get(id=bot_id)
            bot_type = 'quantum_ai'
        else:
            return Response({
                'error': 'Bot not found',
                'code': 'BOT_NOT_FOUND'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get performance data based on bot type
        if bot_type in ['webhook', 'grid', 'martingale']:
            orders = Order.objects.filter(user=user).filter(
                Q(webhook_alert=bot) if bot_type == 'webhook' else
                Q(grid_bot=bot) if bot_type == 'grid' else
                Q(martingale_bot=bot) if bot_type == 'martingale' else
                Q(Q(quantum_bot=bot) if bot_type == 'quantum_ai' else Q())
            ).order_by('-Time')
        else:
            orders = Order.objects.filter(user=user).order_by('-Time')

        # Calculate performance metrics
        if orders.exists():
            recent_orders = orders[:100]  # Last 100 orders
            total_pnl = orders.aggregate(total=Sum('profit_loss'))['total'] or 0
            successful_trades = orders.filter(
                profit_loss__gt=0
            ).count()

            success_rate = (successful_trades / len(recent_orders)) * 100 if recent_orders else 0

            return Response({
                'bot_id': str(bot_id),
                'bot_type': bot_type,
                'bot_name': bot.bot_name if hasattr(bot, 'bot_name') else f'{bot_type.title()} Bot',
                'total_orders': orders.count(),
                'recent_orders': len(recent_orders),
                'total_profit_loss': float(total_pnl),
                'success_rate': success_rate,
                'avg_profit_per_trade': float(total_pnl / len(recent_orders)) if recent_orders else 0,
                'last_trade_date': orders.first().created_at.isoformat() if orders.exists() else None
            })
        else:
            return Response({
                'bot_id': str(bot_id),
                'bot_type': bot_type,
                'bot_name': bot.bot_name if hasattr(bot, 'bot_name') else f'{bot_type.title()} Bot',
                'total_orders': 0,
                'recent_orders': 0,
                'total_profit_loss': 0,
                'success_rate': 0,
                'avg_profit_per_trade': 0,
                'last_trade_date': None
            })

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)