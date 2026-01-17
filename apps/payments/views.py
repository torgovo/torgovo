"""
Views for payment processing endpoints
"""
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

"""
Views for bot management and trading operations
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
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.views import APIView

from apps.bots.models import (
    CustomBot, GridBot, MartingaleBot,
    QuantumAIFund, QuantumAIInvestment,
    PairConfig, Order, Indicator,
    TelegramSignalSubscription, TelegramSignalPlan
)
from apps.bots.serializers import (
    CustomBotSerializer, CustomBotCreateSerializer,
    GridBotSerializer, GridBotCreateSerializer,
    MartingaleBotSerializer, MartingaleBotCreateSerializer,
    QuantumAIFundSerializer, QuantumAIInvestmentSerializer,
    PairConfigSerializer, OrderSerializer, IndicatorSerializer,
    TelegramSignalSubscriptionSerializer, TelegramSignalPlanSerializer
)
from apps.payments.models import BotSubscription, BotSubscriptionPlan
from services.subscription_service import SubscriptionService
from services.bot_executor import BotExecutorService
from services.quantum_ai_fund import QuantumAIFundService
from trading.manager import trading_manager

logger = logging.getLogger('bots')

from .models import (
    SubscriptionPlan, QuantumAIDeposit, BlockchainAddress,
    WithdrawalRequest, PaymentTransaction, ReferralPayout
)
from .serializers import (
    SubscriptionPlanSerializer, QuantumAIDepositSerializer,
    BlockchainAddressSerializer, WithdrawalRequestSerializer,
    PaymentTransactionSerializer, ReferralPayoutSerializer,
    BotSubscriptionSerializer
)
from apps.bots.models import QuantumAIFund, QuantumAIInvestment

logger = logging.getLogger('apps')

class CustomBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Custom TradingView webhook bots
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return CustomBot.objects.all()
        return CustomBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return CustomBotCreateSerializer
        return CustomBotSerializer

    def perform_create(self, serializer):
        # Check if user has active subscription
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='custom',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Custom Bot subscription")

        # Generate webhook credentials
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



class GridBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Grid Trading bots
    """
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
        # Check if user has active subscription
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='grid',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Grid Bot subscription")

        # ENFORCE: 1 bot per subscription
        existing_bot = GridBot.objects.filter(
            subscription=subscription,
            is_deleted=False
        ).first()
        
        if existing_bot:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You already have a Grid Bot for this subscription. "
                "You can update the existing bot's settings (pair, exchange, amount) instead."
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
            success = BotExecutorService.start_grid_bot(request.user, str(bot.id))
            if success:
                return Response({'success': True, 'message': 'Grid bot started'})
            return Response({'error': 'Failed to start bot'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop the grid bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        try:
            success = BotExecutorService.stop_grid_bot(request.user, str(bot.id))
            if success:
                return Response({'success': True, 'message': 'Grid bot stopped'})
            return Response({'error': 'Failed to stop bot'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing subscription plans.
    """
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]


# ==================== MARTINGALE BOT VIEWS ====================

class MartingaleBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Martingale bots
    """
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
        # Check if user has active subscription
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='martingale',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Martingale Bot subscription")

        # ENFORCE: 1 bot per subscription
        existing_bot = MartingaleBot.objects.filter(
            subscription=subscription,
            is_deleted=False
        ).first()
        
        if existing_bot:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "You already have a Martingale Bot for this subscription. "
                "You can update the existing bot's settings (pair, exchange, amount) instead."
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

        # Use same service as grid bot (config differs)
        try:
            config = {
                'bot_name': bot.bot_name,
                'exchange_name': bot.exchange_name,
                'trading_pair': bot.trading_pair,
                'base_amount': float(bot.base_amount),
                'favor_levels': bot.favor_levels,
                'against_levels': bot.against_levels,
                'bot_type': 'martingale',
            }

            bot_instance = trading_manager.create_bot(request.user, 'martingale', config)
            if bot_instance:
                success = trading_manager.start_bot(request.user, 'martingale', config)
                if success:
                    bot.is_running = True
                    bot.started_at = timezone.now()
                    bot.save()
                    return Response({'success': True, 'message': 'Martingale bot started'})

            return Response({'error': 'Failed to start bot'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop the martingale bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        try:
            config = {
                'bot_name': bot.bot_name,
                'exchange_name': bot.exchange_name,
                'trading_pair': bot.trading_pair,
                'bot_type': 'martingale',
            }

            success = trading_manager.stop_bot(request.user, 'martingale', config)
            if success:
                bot.is_running = False
                bot.stopped_at = timezone.now()
                bot.save()
                return Response({'success': True, 'message': 'Martingale bot stopped'})

            return Response({'error': 'Failed to stop bot'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== QUANTUM AI VIEWS ====================

class QuantumAIFundViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Quantum AI Fund (Admin read-only)
    """
    permission_classes = [IsAdminUser]
    queryset = QuantumAIFund.objects.all()
    serializer_class = QuantumAIFundSerializer


class QuantumAIInvestmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user's Quantum AI investments
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return QuantumAIInvestment.objects.all()
        return QuantumAIInvestment.objects.filter(user=self.request.user)

    serializer_class = QuantumAIInvestmentSerializer

    def perform_create(self, serializer):
        # Check if user has active subscription
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type='quantum_ai',
            status='active'
        ).first()

        if not subscription:
            raise PermissionError("No active Quantum AI subscription")

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get user's Quantum AI dashboard"""
        try:
            dashboard = QuantumAIFundService.get_user_dashboard(request.user)
            return Response(dashboard)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PAIR CONFIG VIEWS ====================

class PairConfigViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PairConfig
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return PairConfig.objects.all()
        return PairConfig.objects.filter(user=self.request.user)

    serializer_class = PairConfigSerializer

    def perform_create(self, serializer):
        # Check if user has subscription for this bot_type
        bot_type = serializer.validated_data.get('bot_type', 'grid')
        subscription = BotSubscription.objects.filter(
            user=self.request.user,
            plan__bot_type=bot_type,
            status='active'
        ).first()

        if not subscription:
            raise PermissionError(f"No active subscription for {bot_type} bot")

        serializer.save(user=self.request.user, subscription=subscription)


# ==================== INDICATOR VIEWS ====================

class IndicatorViewSet(viewsets.ModelViewSet):
    """
    ViewSet for technical indicators
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Indicator.objects.all()
        return Indicator.objects.filter(user=self.request.user)

    serializer_class = IndicatorSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ==================== ORDER VIEWS ====================

class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for orders (read-only for history)
    """
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
            'custom_bot', 'grid_bot', 'martingale_bot', 'quantum_ai_investment'
        )[:50]
        serializer = self.get_serializer(recent_orders, many=True)
        return Response(serializer.data)


# ==================== TELEGRAM SIGNALS VIEWS ====================

class TelegramSignalPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Telegram signal plans (read-only)
    """
    permission_classes = [IsAuthenticated]
    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer


class TelegramSignalSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Telegram signal subscriptions
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return TelegramSignalSubscription.objects.all()
        return TelegramSignalSubscription.objects.filter(user=self.request.user)

    serializer_class = TelegramSignalSubscriptionSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ==================== SUBSCRIPTION VIEWS ====================

class BotSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user's bot subscriptions (read-only)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BotSubscriptionSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return BotSubscription.objects.all().select_related('plan', 'user')
        return BotSubscription.objects.filter(user=self.request.user).select_related('plan')


class CreateBotSubscriptionView(APIView):
    """
    Create a new bot subscription (user initiates)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create subscription and upload payment proof"""
        try:
            plan_id = request.data.get('plan_id')
            exchange_name = request.data.get('exchange_name', '')
            payment_screenshot = request.FILES.get('payment_screenshot')
            payment_transaction_hash = request.data.get('payment_transaction_hash', '')
            payment_blockchain = request.data.get('payment_blockchain', '')

            if not plan_id:
                return Response({'error': 'plan_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            if not payment_screenshot and not payment_transaction_hash:
                return Response({'error': 'Either payment_screenshot or payment_transaction_hash is required'}, status=status.HTTP_400_BAD_REQUEST)

            plan = BotSubscriptionPlan.objects.get(id=plan_id)

            # Determine initial status based on payment proof availability
            # If payment proof is provided, move directly to pending_approval
            # Otherwise, set to pending_payment (user needs to upload proof)
            initial_status = 'pending_approval' if (payment_screenshot or payment_transaction_hash) else 'pending_payment'

            # Create subscription
            subscription = BotSubscription.objects.create(
                user=request.user,
                plan=plan,
                exchange_name=exchange_name,
                payment_screenshot=payment_screenshot,
                payment_transaction_hash=payment_transaction_hash,
                payment_blockchain=payment_blockchain,
                status=initial_status,  # Set based on payment proof
            )

            return Response({
                'success': True,
                'message': 'Subscription created and pending approval',
                'subscription_id': str(subscription.id),
                'status': subscription.status,
            }, status=status.HTTP_201_CREATED)

        except BotSubscriptionPlan.DoesNotExist:
            return Response({'error': 'Invalid plan_id'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating subscription: {str(e)}")
            return Response({'error': 'Failed to create subscription'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== WEBHOOK VIEWS ====================
# Note: Custom Bot webhook has been moved to apps/webhooks/views.py
# URL: /api/webhooks/custombot/


# ==================== ADMIN APPROVAL VIEWS ====================

class AdminApproveSubscriptionView(APIView):
    """
    Admin approval endpoint for subscriptions
    """
    permission_classes = [IsAdminUser]

    def post(self, request, subscription_id):
        """Approve a pending subscription"""
        try:
            subscription = SubscriptionService.approve_subscription(subscription_id, request.user)
            return Response({
                'success': True,
                'message': f'Subscription approved for {subscription.user.email}',
                'subscription_id': str(subscription.id)
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminRejectSubscriptionView(APIView):
    """
    Admin rejection endpoint for subscriptions
    """
    permission_classes = [IsAdminUser]

    def post(self, request, subscription_id):
        """Reject a pending subscription"""
        try:
            reason = request.data.get('reason', '')
            if not reason:
                return Response({'error': 'Reason is required'}, status=status.HTTP_400_BAD_REQUEST)

            subscription = SubscriptionService.reject_subscription(subscription_id, request.user, reason)
            return Response({
                'success': True,
                'message': f'Subscription rejected: {reason}',
                'subscription_id': str(subscription.id)
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
# ==================== QUANTUM AI VIEWS ====================

class QuantumDepositViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Quantum AI deposits.
    """
    queryset = QuantumAIDeposit.objects.all()
    serializer_class = QuantumAIDepositSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return QuantumAIDeposit.objects.all().order_by('-created_at')
        return QuantumAIDeposit.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending deposits."""
        if not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        pending_deposits = QuantumAIDeposit.objects.filter(status='pending').order_by('-created_at')
        serializer = self.get_serializer(pending_deposits, many=True)
        return Response(serializer.data)


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing withdrawal requests.
    """
    queryset = WithdrawalRequest.objects.all()
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return WithdrawalRequest.objects.all().order_by('-created_at')
        return WithdrawalRequest.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', '')
        )

    def get_client_ip(self):
        """Get client IP address."""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = self.request.META.get('REMOTE_ADDR', '')
        return ip

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a withdrawal request."""
        withdrawal = self.get_object()

        if withdrawal.user != request.user and not request.user.is_staff:
            return Response({
                'success': False,
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        if withdrawal.status not in ['pending', 'processing']:
            return Response({
                'success': False,
                'error': 'Withdrawal cannot be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)

        withdrawal.status = 'rejected'
        withdrawal.admin_notes = request.data.get('notes', 'Cancelled by user')
        withdrawal.save()

        return Response({
            'success': True,
            'message': 'Withdrawal request cancelled successfully'
        })


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing payment transaction history.
    """
    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return PaymentTransaction.objects.all().order_by('-created_at')
        return PaymentTransaction.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent transactions."""
        recent_transactions = self.get_queryset()[:20]
        serializer = self.get_serializer(recent_transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Filter transactions by type."""
        transaction_type = request.query_params.get('type', None)
        if transaction_type:
            transactions = self.get_queryset().filter(transaction_type=transaction_type)
            serializer = self.get_serializer(transactions, many=True)
            return Response(serializer.data)
        return Response({'error': 'Transaction type parameter required'},
                      status=status.HTTP_400_BAD_REQUEST)


class BlockchainAddressListView(generics.ListAPIView):
    """
    List available blockchain addresses for deposits.
    """
    serializer_class = BlockchainAddressSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return BlockchainAddress.objects.filter(is_active=True)


class CreateDepositView(APIView):
    """
    Create a new deposit for a Quantum AI bot.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=QuantumAIDepositSerializer,
        responses={201: QuantumAIDepositSerializer}
    )
    def post(self, request, bot_id):
        """Create a deposit for the specified bot."""
        try:
            bot = get_object_or_404(QuantumAIFund, id=bot_id, user=request.user)
            
            serializer = QuantumAIDepositSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user, quantum_bot=bot)
                
                return Response({
                    'success': True,
                    'message': 'Deposit created successfully',
                    'deposit': serializer.data
                }, status=status.HTTP_201_CREATED)
            
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error creating deposit: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to create deposit'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApproveDepositView(APIView):
    """
    Approve a pending deposit (admin only).
    """
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'notes': openapi.Schema(type=openapi.TYPE_STRING),
                'usdt_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
            }
        ),
        responses={200: openapi.Response('Deposit approved')}
    )
    def post(self, request, deposit_id):
        """Approve a deposit."""
        try:
            deposit = get_object_or_404(QuantumAIDeposit, id=deposit_id)
            
            if deposit.status != 'pending':
                return Response({
                    'success': False,
                    'error': 'Deposit is not in pending status'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            notes = request.data.get('notes', '')
            usdt_amount = request.data.get('usdt_amount')
            
            if usdt_amount:
                deposit.usdt_amount = Decimal(str(usdt_amount))
            
            deposit.approve(request.user, notes)
            
            return Response({
                'success': True,
                'message': 'Deposit approved successfully'
            })
            
        except Exception as e:
            logger.error(f"Error approving deposit {deposit_id}: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to approve deposit'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RejectDepositView(APIView):
    """
    Reject a pending deposit (admin only).
    """
    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Reason for rejection'),
            },
            required=['reason']
        ),
        responses={200: openapi.Response('Deposit rejected')}
    )
    def post(self, request, deposit_id):
        """Reject a deposit."""
        try:
            deposit = get_object_or_404(QuantumAIDeposit, id=deposit_id)
            
            if deposit.status != 'pending':
                return Response({
                    'success': False,
                    'error': 'Deposit is not in pending status'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            reason = request.data.get('reason', '')
            if not reason:
                return Response({
                    'success': False,
                    'error': 'Reason is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            deposit.reject(request.user, reason)
            
            return Response({
                'success': True,
                'message': 'Deposit rejected successfully'
            })
            
        except Exception as e:
            logger.error(f"Error rejecting deposit {deposit_id}: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to reject deposit'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# ==================== QUANTUM AI ADMIN VIEWS (From Old Code) ====================

@method_decorator(csrf_exempt, name='dispatch')
class IndicatorView(View):
    """Old endpoint for Binance indicators - admin only"""

    async def get(self, request, username, pair):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user,
                slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)

            # Updated to use new TradingManager
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
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user,
                slug=pair
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


@method_decorator(csrf_exempt, name='dispatch')
class CustomOrderClosingView(View):
    """Manual order close endpoint - admin only"""

    async def get(self, request, username, pair):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user,
                slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, user.exchange or 'binance')

            # Call close method if exists
            if hasattr(bot, 'close_custom_order'):
                await bot.close_custom_order()

            return JsonResponse({"message": "Order Closed"}, status=200)

        except Exception as e:
            logger.error(f"Error closing order: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


class CustomOrderOpeningView(View):
    """Manual order open endpoint - admin only"""

    async def get(self, request, username, pair, side):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = await sync_to_async(User.objects.get)(username=username)
            pair_config = await sync_to_async(PairConfig.objects.get)(
                user=user,
                slug=pair
            )
            pair_config_dict = PairConfigSerializer(pair_config)
            bot = await get_or_create_bot(user, pair_config_dict, user.exchange or 'binance')

            # Call open method
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
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "EMA200" in data:
                username = data["username"]
                pair_symbol = data["pair"]
                exchange = data.get("exchange", "binance")
                ema_value = data["EMA200"]

                from django.contrib.auth import get_user_model
                User = get_user_model()

                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user,
                    pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config)
                bot = await get_or_create_bot(user, pair_config_dict, exchange)

                if hasattr(bot, 'update_conditions'):
                    bot.EMA = ema_value
                    bot.pair_config = pair_config_dict.data
                    bot.update_conditions()

                return JsonResponse({
                    'status': 'success',
                    'message': f'EMA updated for {pair_symbol}',
                    'EMA': ema_value
                })

            return JsonResponse({"message": "No EMA data"})

        except Exception as e:
            logger.error(f"Error in BinanceEMA view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceRSIView(View):
    """Webhook endpoint for RSI updates"""

    async def post(self, request):
        try:
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "RSI" in data:
                username = data["username"]
                pair_symbol = data["pair"]
                exchange = data["exchange"]
                rsi_value = data["RSI"]
                PrevRSI = data.get('PrevRSI', 0)
                RSI_color = data.get('color', '')
                RSI_prev_color = data.get('prev_color', '')

                from django.contrib.auth import get_user_model
                User = get_user_model()

                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user,
                    pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config)
                bot = await get_or_create_bot(user, pair_config_dict, exchange)

                if hasattr(bot, 'update_conditions'):
                    bot.RSI = rsi_value
                    bot.PrevRSI = PrevRSI
                    bot.RSI_color = RSI_color
                    bot.RSI_prev_color = RSI_prev_color
                    bot.pair_config = pair_config_dict.data
                    bot.update_conditions()

                return JsonResponse({
                    'status': 'success',
                    'message': f'RSI updated for {pair_symbol}',
                    'RSI': rsi_value
                })

            return JsonResponse({"message": "No RSI data"})

        except Exception as e:
            logger.error(f"Error in BinanceRSI view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceBBView(View):
    """Webhook endpoint for BB updates"""

    async def post(self, request):
        try:
            raw_data = request.body.decode('utf-8').strip('"')
            data = json.loads(raw_data)

            if "BB" in data:
                username = data["username"]
                pair_symbol = data["pair"]
                exchange = data["exchange"]
                bb_value = data["BB"]

                from django.contrib.auth import get_user_model
                User = get_user_model()

                user = await sync_to_async(User.objects.get)(username=username)
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user,
                    pair_symbol=pair_symbol
                )
                pair_config_dict = PairConfigSerializer(pair_config)
                bot = await get_or_create_bot(user, pair_config_dict, exchange)

                if hasattr(bot, 'update_conditions'):
                    bot.BB = bb_value
                    bot.pair_config = pair_config_dict.data
                    bot.update_conditions()

                return JsonResponse({
                    'status': 'success',
                    'message': f'BB updated for {pair_symbol}',
                    'BB': bb_value
                })

            return JsonResponse({"message": "No BB data"})

        except Exception as e:
            logger.error(f"Error in BinanceBB view: {str(e)}")
            return JsonResponse({"error": "Invalid request"}, status=400)


# ==================== HELPER FUNCTIONS (From Old Code) ====================

async def get_or_create_bot(user, pair_config, exchange):
    """Helper to get or create bot via TradingManager"""
    try:
        get_bot = sync_to_async(trading_manager.get_bot)
        bot = await get_bot(user, pair_config.data['pair_symbol'], exchange)

        if not bot:
            print("BOT NOT PRESENT, CREATING NEW ONE")
            create_bot = sync_to_async(trading_manager.create_bot)
            bot = await create_bot(
                user=user,
                pair_config=pair_config.data,
                exchange=exchange
            )
        else:
            print("BOT PRESENT, WILL CHECK IF ITS RUNNING")

    except Exception as e:
        print(f"EXCEPTION HANDLED, CREATING NEW BOT: {e}")
        create_bot = sync_to_async(trading_manager.create_bot)
        bot = await create_bot(
            user=user,
            pair_config=pair_config.data,
            exchange=exchange
        )

    # Ensure bot is started
    start_bot = sync_to_async(trading_manager.start_bot)
    await start_bot(
        user=user,
        pair_symbol=pair_config.data['pair_symbol'],
        exchange=exchange
    )

    return bot

