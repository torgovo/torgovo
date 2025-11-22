"""
Admin-only views for user management
"""
from django.contrib.auth import get_user_model
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from apps.bots.models import WebhookAlert, GridBot, MartingaleBot, QuantumAIBot, Order, BlockchainAddress
from core.permissions import IsAdminUser
from core.pagination import StandardResultsSetPagination
from .admin_serializers import UserAdminSerializer, UserAdminDetailSerializer

User = get_user_model()


class UserListView(generics.ListAPIView):
    """List all users (admin only)."""
    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'is_staff', 'date_joined']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Annotate with additional fields
        queryset = queryset.annotate(
            total_deposits=Count('quantum_deposits', distinct=True),
            active_bots_count=Count(
                Q(webhook_alerts__is_active=True, grid_bots__is_running=True) |
                Q(martingale_bots__is_running=True, quantum_ai_bots__is_active=True),
                distinct=True
            )
        ).select_related('profile')

        return queryset


class UserDetailView(generics.RetrieveUpdateAPIView):
    """Get or update user details (admin only)."""
    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminDetailSerializer

    def get_queryset(self):
        return super().get_queryset().select_related('profile')


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    """Get comprehensive admin dashboard statistics."""
    try:
        # Time ranges
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        last_7_days = today - timedelta(days=7)

        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(
            last_login__gte=last_30_days
        ).count()
        new_users_today = User.objects.filter(
            date_joined__date=today
        ).count()
        new_users_month = User.objects.filter(
            date_joined__gte=last_30_days
        ).count()

        # Subscription statistics
        subscription_stats = {}
        from apps.authentication.models import UserProfile

        for plan_type, display_name in UserProfile.SUBSCRIPTION_PLAN_CHOICES:
            count = UserProfile.objects.filter(
                subscription_plan=plan_type
            ).count()
            subscription_stats[plan_type] = {
                'count': count,
                'display_name': display_name,
                'percentage': (count / total_users * 100) if total_users > 0 else 0
            }

        # Bot statistics
        total_webhooks = WebhookAlert.objects.count()
        total_grid_bots = GridBot.objects.count()
        total_martingale_bots = MartingaleBot.objects.count()
        total_quantum_bots = QuantumAIBot.objects.count()

        running_bots = (
            WebhookAlert.objects.filter(is_active=True).count() +
            GridBot.objects.filter(is_running=True).count() +
            MartingaleBot.objects.filter(is_running=True).count() +
            QuantumAIBot.objects.filter(is_active=True).count()
        )

        # Trading statistics
        from apps.bots.models import Order

        total_trades = Order.objects.count()
        trades_today = Order.objects.filter(
            created_at__date=today
        ).count()
        trades_month = Order.objects.filter(
            created_at__gte=last_30_days
        ).count()

        # Financial statistics
        total_deposits = Deposit.objects.filter(
            status='approved'
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )

        pending_deposits = Deposit.objects.filter(
            status='pending'
        ).count()

        # Exchange distribution
        exchange_stats = {}
        for webhook in WebhookAlert.objects.values('exchange_name').annotate(
            count=Count('id')
        ):
            exchange_stats[webhook['exchange_name']] = webhook['count']

        return Response({
            'user_statistics': {
                'total_users': total_users,
                'active_users': active_users,
                'new_users_today': new_users_today,
                'new_users_month': new_users_month,
                'subscription_distribution': subscription_stats,
            },
            'bot_statistics': {
                'total_bots': total_webhooks + total_grid_bots + total_martingale_bots + total_quantum_bots,
                'running_bots': running_bots,
                'webhook_alerts': total_webhooks,
                'grid_bots': total_grid_bots,
                'martingale_bots': total_martingale_bots,
                'quantum_ai_bots': total_quantum_bots,
                'exchange_distribution': exchange_stats,
            },
            'trading_statistics': {
                'total_trades': total_trades,
                'trades_today': trades_today,
                'trades_month': trades_month,
            },
            'financial_statistics': {
                'total_deposits_usdt': float(total_deposits['total'] or 0),
                'total_deposit_count': total_deposits['count'],
                'pending_deposits': pending_deposits,
            },
        })

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_create_blockchain_address(request):
    """Create new blockchain address for deposits (admin only)."""
    try:
        coin_type = request.data.get('coin_type')
        blockchain = request.data.get('blockchain')
        address = request.data.get('address')

        if not all([coin_type, blockchain, address]):
            return Response({
                'error': 'Missing required fields: coin_type, blockchain, address'
            }, status=status.HTTP_400_BAD_REQUEST)

        blockchain_addr = BlockchainAddress.objects.create(
            coin_type=coin_type,
            blockchain=blockchain,
            address=address,
            admin_only_configurable=True,
            is_active=True
        )

        return Response({
            'message': 'Blockchain address created successfully',
            'address': {
                'id': str(blockchain_addr.id),
                'coin_type': blockchain_addr.coin_type,
                'blockchain': blockchain_addr.blockchain,
                'address': blockchain_addr.address,
                'is_active': blockchain_addr.is_active,
                'admin_only_configurable': blockchain_addr.admin_only_configurable,
                'created_at': blockchain_addr.created_at,
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_bots_overview(request):
    """Get overview of all running bots (admin only)."""
    try:
        # Bot counts by type and status
        webhook_stats = {
            'total': WebhookAlert.objects.count(),
            'active': WebhookAlert.objects.filter(is_active=True).count(),
            'running': 0,  # Webhook alerts don't have running state
            'exchanges': {}
        }

        grid_stats = {
            'total': GridBot.objects.count(),
            'active': GridBot.objects.filter(is_running=True).count(),
            'running': GridBot.objects.filter(is_running=True).count(),
            'exchanges': {}
        }

        martingale_stats = {
            'total': MartingaleBot.objects.count(),
            'active': MartingaleBot.objects.filter(is_running=True).count(),
            'running': MartingaleBot.objects.filter(is_running=True).count(),
            'exchanges': {}
        }

        quantum_stats = {
            'total': QuantumAIBot.objects.count(),
            'active': QuantumAIBot.objects.filter(is_active=True).count(),
            'running': 0,  # Quantum AI bots have different state
            'total_deposited': float(
                QuantumAIBot.objects.aggregate(
                    total=Sum('total_deposited')
                )['total'] or 0
            ),
            'total_profit_loss': float(
                QuantumAIBot.objects.aggregate(
                    total=Sum('current_profit_loss')
                )['total'] or 0
            ),
        }

        # Exchange distribution
        exchanges = ['binance', 'bybit', 'okx', 'mexc', 'alpaca']

        for exchange in exchanges:
            webhook_stats['exchanges'][exchange] = WebhookAlert.objects.filter(
                exchange_name=exchange
            ).count()
            grid_stats['exchanges'][exchange] = GridBot.objects.filter(
                exchange_name=exchange
            ).count()
            martingale_stats['exchanges'][exchange] = MartingaleBot.objects.filter(
                exchange_name=exchange
            ).count()

        return Response({
            'total_bots': (
                webhook_stats['total'] + grid_stats['total'] +
                martingale_stats['total'] + quantum_stats['total']
            ),
            'running_bots': (
                webhook_stats['running'] + grid_stats['running'] +
                martingale_stats['running']
            ),
            'total_users': User.objects.count(),
            'daily_trades': Order.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'platform_volume': float(
                Order.objects.aggregate(
                    total=Sum('quantity')
                )['total'] or 0
            ),
            'by_type': {
                'webhook_alerts': webhook_stats,
                'grid_bots': grid_stats,
                'martingale_bots': martingale_stats,
                'quantum_ai': quantum_stats,
            },
            'by_exchange': {
                exchange: (
                    webhook_stats['exchanges'][exchange] +
                    grid_stats['exchanges'][exchange] +
                    martingale_stats['exchanges'][exchange]
                )
                for exchange in exchanges
            }
        })

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)