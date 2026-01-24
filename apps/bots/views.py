"""
Views for trading bots endpoints
"""
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from apps.bots.models import (
    WebhookAlert, GridBot, MartingaleBot, QuantumAIBot, Order
)
from rest_framework import serializers


# Simple serializers
class WebhookAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookAlert
        fields = '__all__'


class GridBotSerializer(serializers.ModelSerializer):
    class Meta:
        model = GridBot
        fields = '__all__'


class MartingaleBotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MartingaleBot
        fields = '__all__'


class QuantumAIBotSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuantumAIBot
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'


# ViewSets
class WebhookAlertViewSet(viewsets.ModelViewSet):
    """
    ViewSet for webhook alert bots
    """
    queryset = WebhookAlert.objects.all()
    serializer_class = WebhookAlertSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class GridBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for grid bots
    """
    queryset = GridBot.objects.all()
    serializer_class = GridBotSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class MartingaleBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for martingale bots
    """
    queryset = MartingaleBot.objects.all()
    serializer_class = MartingaleBotSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class QuantumAIBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for quantum AI bots
    """
    queryset = QuantumAIBot.objects.all()
    serializer_class = QuantumAIBotSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for orders
    """
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


# Function-based views for bot control
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_grid_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_grid_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_martingale_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_martingale_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_quantum_ai_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_quantum_ai_bot(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bots_overview(request):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bot_performance(request, bot_id):
    return Response({'message': 'Not implemented yet'}, status=status.HTTP_501_NOT_IMPLEMENTED)


from apps.trading.engines.bot_engine import BotEngine
from apps.trading.models import TradingBot, ExchangeCredentials, StrategyConfig

async def get_or_create_bot(user, pair_config_dict, exchange):
    """
    Get existing TradingBot or create new one, return BotEngine.
    """
    symbol = pair_config_dict['pair_symbol']
    
    # Get exchange credentials
    creds = await sync_to_async(ExchangeCredentials.objects.get)(
        user=user,
        exchange_name=exchange
    )
    
    # Get strategy config
    strategy = await sync_to_async(StrategyConfig.objects.get)(
        strategy='quantum_ai'
    )
    
    # Get or create TradingBot
    bot_name = f"{user.username}_{symbol}_{exchange}"
    bot, created = await sync_to_async(TradingBot.objects.get_or_create)(
        user=user,
        name=bot_name,
        defaults={
            'strategy': strategy,
            'exchange_credentials': creds,
            'symbol': symbol,
            'status': 'stopped',
            'max_positions': 3,
            'position_size': float(pair_config_dict.get('quantity', 10)),
            'custom_parameters': {
                'favor_levels': pair_config_dict.get('favor_levels', 3),
                'against_levels': pair_config_dict.get('against_levels', 3),
                'favor_level_qty': pair_config_dict.get('favor_level_qty', 5),
                'against_level_qty': pair_config_dict.get('against_level_qty', 5),
            }
        }
    )
    
    # Create engine
    engine = BotEngine(bot)
    
    if created:
        logger.info(f"🤖 Created new bot: {bot_name}")
    else:
        logger.debug(f"✅ Found existing bot: {bot_name}")
    
    return engine

# In your BinanceEMA view:
async def post(self, request):
    # ... parse data ...
    engine = await get_or_create_bot(user, pair_config_dict, exchange)
    engine.EMA = ema_value  # Same as old bot.EMA = value
    result = engine.update_conditions()  # Same as old bot.update_conditions()
    return JsonResponse({'success': True, 'result': result})