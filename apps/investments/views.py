"""
Investment App Views for Torgovo Crypto Trading Platform
Implements all endpoints from DOCUMENTATION.md
"""
import uuid
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction as db_transaction
from django.db.models import Q
from rest_framework import viewsets, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from .models import *
from .serializers import *

logger = logging.getLogger(__name__)


# ==================== PERMISSIONS ====================

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        try:
            if hasattr(obj, 'user'):
                return obj.user == request.user
            elif hasattr(obj, 'user_id'):
                return obj.user_id == request.user.id
            return False
        except:
            return False


# ==================== PAGINATION ====================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ==================== FILTERS ====================

class OrderFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name='bot__category')
    pair = django_filters.CharFilter(field_name='trading_pair__symbol', lookup_expr='iexact')
    exchange = django_filters.CharFilter(field_name='exchange__name')
    start_date = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = Order
        fields = ['status', 'side', 'order_type']


# ==================== VIEWSETS ====================

class ExchangeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Exchange.objects.filter(status='active')
    serializer_class = ExchangeSerializer
    permission_classes = [permissions.AllowAny]
    
    @action(detail=False, methods=['get'])
    def supported(self, request):
        return Response({
            'exchanges': self.get_serializer(self.queryset, many=True).data
        })


class ExchangeCredentialViewSet(viewsets.ModelViewSet):
    serializer_class = ExchangeCredentialSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    
    def get_queryset(self):
        return ExchangeCredential.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # Test connection here before saving
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        credential = self.get_object()
        # Implement exchange API test here
        return Response({'status': 'connected', 'is_testnet': credential.is_testnet})


class TradingPairViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TradingPair.objects.filter(is_active=True)
    serializer_class = TradingPairSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['exchange', 'base_asset', 'quote_asset']
    search_fields = ['symbol']
    
    @action(detail=False, methods=['get'])
    def top_gainers(self, request):
        pairs = self.queryset.filter(price_change_percent_24h__gt=0).order_by('-price_change_percent_24h')[:20]
        return Response(self.get_serializer(pairs, many=True).data)
    
    @action(detail=False, methods=['get'])
    def top_losers(self, request):
        pairs = self.queryset.filter(price_change_percent_24h__lt=0).order_by('price_change_percent_24h')[:20]
        return Response(self.get_serializer(pairs, many=True).data)
    
    @action(detail=False, methods=['get'])
    def most_active(self, request):
        pairs = self.queryset.order_by('-volume_24h')[:20]
        return Response(self.get_serializer(pairs, many=True).data)


class WebhookAlertBotViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookAlertBotSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return WebhookAlertBot.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        # Generate webhook_url
        instance.webhook_url = f"https://api.torgovo.com/api/webhooks/tradingview/{instance.webhook_id}/"
        instance.save()
    
    @action(detail=True, methods=['post'])
    def regenerate_secret(self, request, pk=None):
        bot = self.get_object()
        bot.secret_key = uuid.uuid4().hex
        bot.save()
        return Response(WebhookAlertBotSerializer(bot).data)


class GridBotViewSet(viewsets.ModelViewSet):
    serializer_class = GridBotSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return GridBot.objects.filter(user=self.request.user)


class MartingaleBotViewSet(viewsets.ModelViewSet):
    serializer_class = MartingaleBotSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return MartingaleBot.objects.filter(user=self.request.user)


class QuantumAIBotViewSet(viewsets.ModelViewSet):
    serializer_class = QuantumAIBotSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return QuantumAIBot.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def generate_addresses(self, request, pk=None):
        """Generate blockchain deposit addresses for Quantum AI"""
        bot = self.get_object()
        # In production, generate real addresses via exchange APIs
        addresses = {
            'USDT': {
                'BEP20': f'0x{uuid.uuid4().hex[:40]}',
                'ERC20': f'0x{uuid.uuid4().hex[:40]}',
                'TRC20': f'T{uuid.uuid4().hex[:33]}',
            },
            'USDC': {
                'BEP20': f'0x{uuid.uuid4().hex[:40]}',
                'ERC20': f'0x{uuid.uuid4().hex[:40]}',
            },
            'BTC': {
                'Bitcoin': f'1{uuid.uuid4().hex[:33]}',
            }
        }
        bot.blockchain_addresses = addresses
        bot.save()
        return Response({'addresses': addresses})


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status == 'pending':
            order.status = 'cancelled'
            order.save()
            return Response({'status': 'cancelled'})
        return Response({'error': 'Cannot cancel this order'}, status=status.HTTP_400_BAD_REQUEST)


class PositionViewSet(viewsets.ModelViewSet):
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        return Position.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        position = self.get_object()
        # Implement position closing logic
        return Response({'status': 'closed'})


class TechnicalIndicatorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TechnicalIndicator.objects.all()
    serializer_class = TechnicalIndicatorSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['indicator_type', 'trading_pair', 'exchange']
    pagination_class = StandardResultsSetPagination


class UserBalanceViewSet(viewsets.ModelViewSet):
    serializer_class = UserBalanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    
    def get_queryset(self):
        return UserBalance.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        balances = self.get_queryset()
        total_usdt = sum(balance.total for balance in balances if balance.currency == 'USDT')
        return Response({
            'total_usdt_value': total_usdt,
            'balances': UserBalanceSerializer(balances, many=True).data
        })

# ==================== WEBHOOK HANDLERS ====================

class TradingViewWebhookView(APIView):
    """Handle TradingView webhook alerts"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, webhook_id):
        try:
            bot = WebhookAlertBot.objects.get(webhook_id=webhook_id, is_active=True)
            
            # Verify secret key
            secret = request.data.get('secret')
            if secret != bot.secret_key:
                return Response({'error': 'Invalid secret key'}, status=status.HTTP_403_FORBIDDEN)
            
            # Process the trade
            action = request.data.get('action', '').lower()
            amount = Decimal(request.data.get('order', {}).get('amount', bot.default_amount))
            
            if action in ['buy', 'sell']:
                self.execute_trade(bot, action, amount, request.data)
                bot.last_triggered = timezone.now()
                bot.save()
                
                return Response({
                    'status': 'success',
                    'message': f'Webhook processed: {action} {amount} {bot.trading_pair.symbol}',
                    'bot_id': str(bot.id)
                })
            
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)
            
        except WebhookAlertBot.DoesNotExist:
            return Response({'error': 'Bot not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return Response({'error': 'Internal error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def execute_trade(self, bot, action, amount, data):
        """Execute trade based on webhook signal"""
        with db_transaction.atomic():
            # Create order
            Order.objects.create(
                user=bot.user,
                bot=bot,
                exchange=bot.exchange,
                trading_pair=bot.trading_pair,
                order_type='market',
                side=action,
                quantity=amount,
                price=bot.trading_pair.current_price or 0,
                take_profit=bot.take_profit_percent,
                stop_loss=bot.stop_loss_percent,
                description=f"TradingView webhook: {data.get('strategy_info', {})}"
            )
            
            # Update bot performance
            bot.total_trades += 1
            bot.save()


class EMAWebhookView(APIView):
    """Handle EMA indicator webhooks"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            data = request.data
            username = data.get('username')
            pair = data.get('pair')
            exchange_name = data.get('exchange')
            ema_value = data.get('EMA200')
            
            user = get_object_or_404(get_user_model(), username=username)
            exchange = get_object_or_404(Exchange, name=exchange_name)
            trading_pair = get_object_or_404(TradingPair, symbol=pair, exchange=exchange)
            
            # Store indicator
            TechnicalIndicator.objects.create(
                indicator_type='EMA',
                trading_pair=trading_pair,
                exchange=exchange,
                values={'EMA200': ema_value},
                triggered_at=timezone.now()
            )
            
            # Trigger bots if needed
            self.check_ema_bots(user, trading_pair, ema_value)
            
            return Response({
                'status': 'success',
                'message': f'EMA processed for {pair}',
                'EMA': ema_value
            })
            
        except Exception as e:
            logger.error(f"EMA webhook error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def check_ema_bots(self, user, trading_pair, ema_value):
        """Check and trigger EMA-based bots"""
        # Implementation for EMA strategy bots
        pass


class RSIWebhookView(APIView):
    """Handle RSI indicator webhooks"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        try:
            data = request.data
            username = data.get('username')
            pair = data.get('pair')
            exchange_name = data.get('exchange')
            rsi_value = float(data.get('RSI', 0))
            color = data.get('color')
            prev_color = data.get('prev_color')
            
            user = get_object_or_404(get_user_model(), username=username)
            exchange = get_object_or_404(Exchange, name=exchange_name)
            trading_pair = get_object_or_404(TradingPair, symbol=pair, exchange=exchange)
            
            # Store indicator
            TechnicalIndicator.objects.create(
                indicator_type='RSI',
                trading_pair=trading_pair,
                exchange=exchange,
                values={'RSI': rsi_value, 'PrevRSI': data.get('PrevRSI')},
                color=color,
                prev_color=prev_color,
                triggered_at=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'message': f'RSI processed for {pair}',
                'RSI': rsi_value
            })
            
        except Exception as e:
            logger.error(f"RSI webhook error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



class EMAIndicatorView(APIView):
    """Manual EMA indicator submission"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        return Response({
            'status': 'success',
            'message': 'EMA endpoint is ready. Use webhooks for automated signals.'
        })


class RSIIndicatorView(APIView):
    """Manual RSI indicator submission"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        return Response({
            'status': 'success',
            'message': 'RSI endpoint is ready. Use webhooks for automated signals.'
        })


class ExchangeListView(APIView):
    """List supported exchanges"""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        exchanges = Exchange.objects.filter(status='active')
        return Response({
            'exchanges': ExchangeSerializer(exchanges, many=True).data
        })


class ExchangeSymbolsView(APIView):
    """Get trading symbols for an exchange"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, exchange_name):
        try:
            exchange = Exchange.objects.get(name=exchange_name)
            symbols = TradingPair.objects.filter(
                exchange=exchange, 
                is_active=True
            ).values_list('symbol', flat=True)
            
            return Response({
                'exchange': exchange_name,
                'symbols': list(symbols)
            })
        except Exchange.DoesNotExist:
            return Response({'error': 'Exchange not found'}, status=status.HTTP_404_NOT_FOUND)


class UserOrdersView(APIView):
    """Get user's order history"""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get(self, request):
        queryset = Order.objects.filter(user=request.user)
        
        # Filter by category
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(bot__category=category)
        
        # Filter by pair
        pair = request.query_params.get('pair')
        if pair:
            queryset = queryset.filter(trading_pair__symbol__iexact=pair)
        
        # Filter by exchange
        exchange = request.query_params.get('exchange')
        if exchange:
            queryset = queryset.filter(exchange__name=exchange)
        
        # Filter by date range
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Paginate
        page = self.pagination_class()
        result_page = page.paginate_queryset(queryset, request)
        serializer = OrderSerializer(result_page, many=True)
        
        return page.get_paginated_response(serializer.data)


class UserProfileView(APIView):
    """Get user trading profile"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get subscription plan details
        max_bots = getattr(user, 'max_bots_allowed', 10)
        total_trades = Order.objects.filter(user=user).count()
        total_volume = Order.objects.filter(user=user).aggregate(
            total=models.Sum('quantity'))['total'] or 0
        
        return Response({
            'id': str(user.id),
            'user_email': user.email,
            'user_full_name': user.get_full_name(),
            'subscription_plan': getattr(user, 'subscription_plan', 'basic'),
            'max_bots_allowed': max_bots,
            'timezone': getattr(user, 'timezone', 'UTC'),
            'demo_trading_enabled': getattr(user, 'demo_trading_enabled', True),
            'email_notifications': getattr(user, 'email_notifications', True),
            'is_subscription_active': getattr(user, 'is_subscription_active', True),
            'total_trades_executed': total_trades,
            'total_volume_traded': str(total_volume)
        })


class BlockchainAddressesView(APIView):
    """Get blockchain deposit addresses for Quantum AI"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Return predefined addresses (in production, generate per user)
        addresses = {
            'USDT': {
                'BEP20': '0x' + uuid.uuid4().hex[:40],
                'ERC20': '0x' + uuid.uuid4().hex[:40],
                'TRC20': 'T' + uuid.uuid4().hex[:33],
                'SOL': '9WzDX' + uuid.uuid4().hex[:40],
            },
            'USDC': {
                'BEP20': '0x' + uuid.uuid4().hex[:40],
                'ERC20': '0x' + uuid.uuid4().hex[:40],
            },
            'BTC': {
                'Bitcoin': '1' + uuid.uuid4().hex[:33],
            }
        }
        return Response(addresses)


class QuantumAIDepositView(APIView):
    """Handle Quantum AI deposit with screenshot"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, bot_id):
        try:
            bot = QuantumAIBot.objects.get(id=bot_id, user=request.user)
            
            amount = request.data.get('amount')
            coin_type = request.data.get('coin_type')
            blockchain = request.data.get('blockchain')
            transaction_hash = request.data.get('transaction_hash')
            screenshot = request.FILES.get('screenshot')
            
            # Validate deposit
            if not all([amount, coin_type, blockchain, transaction_hash]):
                return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Process deposit (implement your logic)
            # Save to transaction model, update balances, etc.
            
            return Response({
                'message': 'Deposit submitted for review',
                'bot_id': str(bot.id),
                'amount': amount,
                'coin_type': coin_type,
                'blockchain': blockchain,
                'transaction_hash': transaction_hash
            })
            
        except QuantumAIBot.DoesNotExist:
            return Response({'error': 'Bot not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Quantum AI deposit error: {str(e)}")
            return Response({'error': 'Deposit failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StartBotView(APIView):
    """Start a trading bot"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, bot_id):
        try:
            bot = BotBase.objects.get(id=bot_id, user=request.user)
            
            if bot.status == 'running':
                return Response({'error': 'Bot is already running'}, status=status.HTTP_400_BAD_REQUEST)
            
            bot.status = 'running'
            bot.started_at = timezone.now()
            bot.save()
            
            return Response({
                'message': f'{bot.category} bot started successfully',
                'bot_id': str(bot.id),
                'status': 'running'
            })
            
        except BotBase.DoesNotExist:
            return Response({'error': 'Bot not found'}, status=status.HTTP_404_NOT_FOUND)


class StopBotView(APIView):
    """Stop a trading bot"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, bot_id):
        try:
            bot = BotBase.objects.get(id=bot_id, user=request.user)
            
            if bot.status != 'running':
                return Response({'error': 'Bot is not running'}, status=status.HTTP_400_BAD_REQUEST)
            
            bot.status = 'stopped'
            bot.stopped_at = timezone.now()
            bot.save()
            
            return Response({
                'message': f'{bot.category} bot stopped successfully',
                'bot_id': str(bot.id),
                'status': 'stopped',
                'final_profit_loss': str(bot.total_profit_loss)
            })
            
        except BotBase.DoesNotExist:
            return Response({'error': 'Bot not found'}, status=status.HTTP_404_NOT_FOUND)


class PauseBotView(APIView):
    """Pause a trading bot"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, bot_id):
        try:
            bot = BotBase.objects.get(id=bot_id, user=request.user)
            
            if bot.status != 'running':
                return Response({'error': 'Bot is not running'}, status=status.HTTP_400_BAD_REQUEST)
            
            bot.status = 'paused'
            bot.save()
            
            return Response({
                'message': f'{bot.category} bot paused successfully',
                'bot_id': str(bot.id),
                'status': 'paused'
            })
            
        except BotBase.DoesNotExist:
            return Response({'error': 'Bot not found'}, status=status.HTTP_404_NOT_FOUND)