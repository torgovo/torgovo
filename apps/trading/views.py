"""
Views for trading endpoints
"""
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import (
    Exchange, ExchangeCredentials, TradingPair, ExchangeStatus,
    SupportedBlockchain, ExchangeRate, BotConfiguration
)
from .serializers import (
    ExchangeSerializer, ExchangeCredentialsSerializer,
    ExchangeCredentialsCreateSerializer, TradingPairSerializer,
    ExchangeStatusSerializer, SupportedBlockchainSerializer,
    ExchangeRateSerializer, BotConfigurationSerializer,
    BotConfigurationCreateSerializer
)

logger = logging.getLogger('apps.trading')


# =============================================================================
# EXCHANGE VIEWSETS
# =============================================================================

class ExchangeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing supported exchanges."""
    serializer_class = ExchangeSerializer
    permission_classes = [IsAuthenticated]
    queryset = Exchange.objects.filter(is_active=True)


class ExchangeCredentialsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing exchange credentials."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ExchangeCredentialsCreateSerializer
        return ExchangeCredentialsSerializer

    def get_queryset(self):
        return ExchangeCredentials.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active exchange credentials."""
        active_credentials = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_credentials, many=True)
        return Response(serializer.data)


class TradingPairViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing available trading pairs."""
    serializer_class = TradingPairSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = TradingPair.objects.filter(is_active=True)
        exchange_name = self.request.query_params.get('exchange', None)
        if exchange_name:
            queryset = queryset.filter(exchange_name=exchange_name)
        return queryset

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get popular trading pairs."""
        popular_pairs = self.get_queryset()[:20]
        serializer = self.get_serializer(popular_pairs, many=True)
        return Response(serializer.data)


class ExchangeStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for exchange status information."""
    serializer_class = ExchangeStatusSerializer
    queryset = ExchangeStatus.objects.all()
    permission_classes = [IsAuthenticated]


# =============================================================================
# BOT CONFIGURATION VIEWSETS
# =============================================================================

class BotConfigurationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing bot configurations."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return BotConfigurationCreateSerializer
        return BotConfigurationSerializer

    def get_queryset(self):
        return BotConfiguration.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a bot."""
        bot = self.get_object()
        if bot.status == 'active':
            return Response({'error': 'Bot is already running'}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Trigger Celery task to start the bot
        bot.status = 'active'
        bot.save()
        return Response({'status': 'Bot started'})

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop a bot."""
        bot = self.get_object()
        if bot.status == 'stopped':
            return Response({'error': 'Bot is already stopped'}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Trigger Celery task to stop the bot
        bot.status = 'stopped'
        bot.save()
        return Response({'status': 'Bot stopped'})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a bot."""
        bot = self.get_object()
        bot.status = 'paused'
        bot.save()
        return Response({'status': 'Bot paused'})


# =============================================================================
# FUNCTION-BASED VIEWS
# =============================================================================

@swagger_auto_schema(
    method='get',
    responses={200: openapi.Response(
        description='List of supported exchanges',
        schema=openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'name': openapi.Schema(type=openapi.TYPE_STRING),
                    'display_name': openapi.Schema(type=openapi.TYPE_STRING),
                    'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                }
            )
        )
    )}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_exchanges(request):
    """List all supported cryptocurrency exchanges."""
    try:
        exchanges = Exchange.objects.filter(is_active=True)
        exchange_data = []

        for exchange in exchanges:
            exchange_data.append({
                'name': exchange.name,
                'display_name': exchange.display_name,
                'is_active': exchange.is_active,
                'supports_testnet': exchange.supports_testnet,
                'supported_features': exchange.supported_features,
                'fee_rates': exchange.fee_rates
            })

        return Response({
            'success': True,
            'data': exchange_data
        })

    except Exception as e:
        logger.error(f"Error listing exchanges: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to retrieve exchanges'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exchange_symbols(request, exchange_name):
    """Get trading symbols for a specific exchange."""
    try:
        pairs = TradingPair.objects.filter(exchange_name=exchange_name, is_active=True)
        symbols = [pair.symbol for pair in pairs]

        return Response({
            'success': True,
            'exchange': exchange_name,
            'symbols': symbols
        })

    except Exception as e:
        logger.error(f"Error getting exchange symbols for {exchange_name}: {str(e)}")
        return Response({
            'success': False,
            'error': f'Failed to retrieve symbols for {exchange_name}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exchange_rates(request):
    """Get current exchange rates for trading pairs."""
    try:
        pairs_param = request.GET.get('pairs', None)
        rates = {}

        if pairs_param:
            symbols = [s.strip().upper() for s in pairs_param.split(',')]
            trading_pairs = TradingPair.objects.filter(
                symbol__in=symbols,
                is_active=True
            )[:50]
        else:
            trading_pairs = TradingPair.objects.filter(is_active=True)[:50]

        for pair in trading_pairs:
            rates[pair.symbol] = {
                'price': Decimal('45000.00'),  # Placeholder
                'exchange': pair.exchange_name,
                'volume_24h': Decimal('1234567.89'),
                'change_24h': Decimal('2.5')
            }

        return Response({
            'success': True,
            'rates': rates,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting exchange rates: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to retrieve exchange rates'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from apps.trading.managers.bot_bridge import BotBridge
from apps.trading.models import TradingBot, ExchangeCredentials, StrategyConfig

async def get_or_create_bot(user, pair_symbol: str, exchange: str):
    """
    Get bot and wrap it in BotBridge (new architecture, same old flow)
    """
    # Get exchange credentials
    creds = await sync_to_async(ExchangeCredentials.objects.get)(
        user=user,
        exchange_name=exchange
    )
    
    # Get strategy
    strategy = await sync_to_async(StrategyConfig.objects.get)(
        strategy='quantum_ai'
    )
    
    # Get or create bot
    bot_name = f"{user.username}_{pair_symbol}_{exchange}"
    bot, created = await sync_to_async(TradingBot.objects.get_or_create)(
        user=user,
        name=bot_name,
        defaults={
            'strategy': strategy,
            'exchange_credentials': creds,
            'symbol': pair_symbol,
            'custom_parameters': {
                'favor_levels': 3,
                'against_levels': 3,
            }
        }
    )
    
    # Create bridge
    bridge = BotBridge(bot)
    
    if created:
        print(f"🤖 Created new bot: {bot_name}")
    
    return bridge

# In your EMA/RSI/BB update views:
async def post(self, request):
    # ... parse data ...
    bridge = await get_or_create_bot(user, symbol, exchange)
    
    # Update indicators (mimics old bot.EMA = value)
    bridge.update_indicator('EMA', ema_value)
    bridge.update_indicator('RSI', rsi_value)
    # ... etc ...
    
    # Execute once (like old bot.update_conditions())
    result = bridge.execute_once()
    
    # Return response
    return JsonResponse({'success': True, 'result': result})