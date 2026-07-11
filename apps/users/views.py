"""
Admin-only views for user management
"""
from django.contrib.auth import get_user_model
from rest_framework import status, generics, permissions, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from datetime import timedelta

from apps.investments.models import WebhookAlertBot as WebhookAlert
from apps.bots.models import GridBot, MartingaleBot, QuantumAIBot, Order
from apps.payments.models import BlockchainAddress, WithdrawalRequest, QuantumAIDeposit as Deposit
from apps.referrals.models import Referral
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
                Q(botbase_bots__is_active=True) |
                Q(grid_bots__is_running=True) |
                Q(martingale_bots__is_running=True) |
                Q(quantum_ai_investments__status='active'),
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

        for plan_type, display_name in UserProfile.SUBSCRIPTION_PLANS:
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
            QuantumAIBot.objects.filter(is_running=True).count()
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
        for webhook in WebhookAlert.objects.values('exchange__name').annotate(
            count=Count('id')
        ):
            exchange_stats[webhook['exchange__name']] = webhook['count']

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
            'active': QuantumAIBot.objects.filter(is_running=True).count(),
            'running': 0,  # Quantum AI bots have different state
            'total_deposited': 0,
            'total_profit_loss': float(
                QuantumAIBot.objects.aggregate(
                    total=Sum('total_profit_loss')
                )['total'] or 0
            ),
        }

        # Exchange distribution
        exchanges = ['binance', 'bybit', 'okx', 'mexc', 'alpaca']

        for exchange in exchanges:
            webhook_stats['exchanges'][exchange] = WebhookAlert.objects.filter(
                exchange__name=exchange
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
                    total=Sum('Quantity')
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


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_trade_logs(request):
    """View all trade logs with filters (admin only)."""
    from rest_framework import filters
    
    queryset = Order.objects.all().select_related('user', 'signal_bot', 'grid_bot', 'martingale_bot')
    
    # Apply filters
    user_id = request.query_params.get('user_id')
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    
    exchange = request.query_params.get('exchange')
    if exchange:
        queryset = queryset.filter(exchange=exchange)
    
    bot_id = request.query_params.get('bot_id')
    if bot_id:
        queryset = queryset.filter(
            Q(signal_bot_id=bot_id) | Q(grid_bot_id=bot_id) | Q(martingale_bot_id=bot_id)
        )
    
    start_date = request.query_params.get('start_date')
    if start_date:
        queryset = queryset.filter(timestamp__gte=start_date)
    
    end_date = request.query_params.get('end_date')
    if end_date:
        queryset = queryset.filter(timestamp__lte=end_date)
    
    # Paginate results
    paginator = StandardResultsSetPagination()
    result_page = paginator.paginate_queryset(queryset, request)
    
    from apps.bots.serializers import OrderSerializer
    serializer = OrderSerializer(result_page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_restrict_user(request, pk):
    """Restrict/disable user account (admin only)."""
    try:
        user = User.objects.get(pk=pk)
        
        action = request.data.get('action', 'disable')
        reason = request.data.get('reason', '')
        
        if action == 'disable':
            user.is_active = False
        elif action == 'enable':
            user.is_active = True
        elif action == 'restrict':
            user.is_active = False
        else:
            return Response(
                {'error': 'Invalid action. Use "enable", "disable", or "restrict"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.save()
        
        return Response({
            'message': f'User {user.email} has been {action}d',
            'user_id': str(user.pk),
            'is_active': user.is_active
        })
    
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_send_email(request):
    """Send emails (system-wide or targeted) (admin only)."""
    email_type = request.data.get('type', 'system')
    subject = request.data.get('subject')
    message = request.data.get('message')
    recipients = request.data.get('recipients', [])  # List of user IDs or 'all'
    
    if not subject or not message:
        return Response(
            {'error': 'Subject and message are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        if email_type == 'system':
            if recipients == 'all':
                users = User.objects.filter(is_active=True)
            else:
                users = User.objects.filter(id__in=recipients, is_active=True)
            
            successful = 0
            failed = 0
            
            for user in users:
                try:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False
                    )
                    successful += 1
                except Exception:
                    failed += 1
            
            return Response({
                'message': f'Email sent to {successful} users',
                'successful': successful,
                'failed': failed
            })
        
        else:
            return Response(
                {'error': 'Invalid email type'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except Exception as e:
        return Response(
            {'error': f'Failed to send emails: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_process_withdrawals(request):
    """Process manual withdrawals every 2 weeks (admin only)."""
    try:
        pending_withdrawals = WithdrawalRequest.objects.filter(status='pending')
        
        if not pending_withdrawals.exists():
            return Response({
                'message': 'No pending withdrawals to process',
                'processed': 0
            })
        
        successful = 0
        failed = 0
        
        for withdrawal in pending_withdrawals:
            try:
                withdrawal.status = 'completed'
                withdrawal.save()
                successful += 1
            except Exception as e:
                withdrawal.status = 'failed'
                withdrawal.error_message = str(e)
                withdrawal.save()
                failed += 1
        
        return Response({
            'message': f'Processed {successful} withdrawals ({failed} failed)',
            'successful': successful,
            'failed': failed
        })
    
    except Exception as e:
        return Response(
            {'error': f'Failed to process withdrawals: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
