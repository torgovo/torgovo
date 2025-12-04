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

from .models import (
    SubscriptionPlan, QuantumAIDeposit, BlockchainAddress,
    WithdrawalRequest, PaymentTransaction, ReferralPayout
)
from .serializers import (
    SubscriptionPlanSerializer, QuantumAIDepositSerializer,
    BlockchainAddressSerializer, WithdrawalRequestSerializer,
    PaymentTransactionSerializer, ReferralPayoutSerializer
)
from apps.bots.models import QuantumAIBot

logger = logging.getLogger('apps')


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing subscription plans.
    """
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]


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
            bot = get_object_or_404(QuantumAIBot, id=bot_id, user=request.user)
            
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