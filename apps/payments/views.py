"""
Views for payment processing endpoints
"""
import logging
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import (
    PaymentMethod, Transaction, Invoice, WithdrawalRequest,
    PaymentGateway, Refund
)
from .serializers import (
    PaymentMethodSerializer, TransactionSerializer,
    InvoiceSerializer, WithdrawalRequestSerializer,
    PaymentGatewaySerializer, RefundSerializer
)

logger = logging.getLogger('apps')


class PaymentMethodViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing payment methods.
    """
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a payment method as default."""
        payment_method = self.get_object()

        # Unset all other payment methods for this user
        PaymentMethod.objects.filter(
            user=request.user,
            payment_type=payment_method.payment_type
        ).update(is_default=False)

        # Set this one as default
        payment_method.is_default = True
        payment_method.save()

        return Response({
            'success': True,
            'message': f'{payment_method.payment_type.title()} payment method set as default'
        })


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing transaction history.
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent transactions."""
        recent_transactions = self.get_queryset()[:10]
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


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing invoices.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Pay an invoice."""
        invoice = self.get_object()

        if invoice.status != 'pending':
            return Response({
                'success': False,
                'error': 'Invoice cannot be paid'
            }, status=status.HTTP_400_BAD_REQUEST)

        payment_method_id = request.data.get('payment_method_id')
        if not payment_method_id:
            return Response({
                'success': False,
                'error': 'Payment method is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment_method = get_object_or_404(
                PaymentMethod,
                id=payment_method_id,
                user=request.user,
                is_active=True
            )

            # Process payment (integrates with payment gateway)
            # This is a simplified version
            transaction = Transaction.objects.create(
                user=request.user,
                invoice=invoice,
                amount=invoice.amount,
                transaction_type='payment',
                status='completed',
                payment_method=payment_method
            )

            # Update invoice status
            invoice.status = 'paid'
            invoice.paid_at = timezone.now()
            invoice.save()

            return Response({
                'success': True,
                'message': 'Invoice paid successfully',
                'transaction_id': transaction.id
            })

        except Exception as e:
            logger.error(f"Error paying invoice {invoice.id}: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to process payment'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def receipt(self, request, pk=None):
        """Get invoice receipt details."""
        invoice = self.get_object()

        if invoice.status != 'paid':
            return Response({
                'success': False,
                'error': 'Invoice is not paid'
            }, status=status.HTTP_400_BAD_REQUEST)

        transaction = Transaction.objects.filter(
            invoice=invoice,
            status='completed'
        ).first()

        if not transaction:
            return Response({
                'success': False,
                'error': 'No transaction found for this invoice'
            }, status=status.HTTP_404_NOT_FOUND)

        receipt_data = {
            'invoice': {
                'id': invoice.id,
                'number': invoice.invoice_number,
                'amount': invoice.amount,
                'description': invoice.description,
                'created_at': invoice.created_at,
                'paid_at': invoice.paid_at
            },
            'transaction': {
                'id': transaction.id,
                'amount': transaction.amount,
                'transaction_id': transaction.transaction_id,
                'payment_method': transaction.payment_method.method_type if transaction.payment_method else None,
                'completed_at': transaction.updated_at
            },
            'user': {
                'email': request.user.email,
                'name': request.user.get_full_name() or request.user.email
            }
        }

        return Response({
            'success': True,
            'receipt': receipt_data
        })


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing withdrawal requests.
    """
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a withdrawal request."""
        withdrawal = self.get_object()

        if withdrawal.status not in ['pending', 'processing']:
            return Response({
                'success': False,
                'error': 'Withdrawal cannot be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)

        withdrawal.status = 'cancelled'
        withdrawal.cancelled_at = timezone.now()
        withdrawal.notes = request.data.get('notes', withdrawal.notes)
        withdrawal.save()

        return Response({
            'success': True,
            'message': 'Withdrawal request cancelled successfully'
        })


class PaymentGatewayViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for payment gateway information.
    """
    serializer_class = PaymentGatewaySerializer
    queryset = PaymentGateway.objects.filter(is_active=True)

    @action(detail=True, methods=['get'])
    def supported_methods(self, request, pk=None):
        """Get supported payment methods for a gateway."""
        gateway = self.get_object()
        return Response({
            'success': True,
            'gateway': gateway.name,
            'supported_methods': gateway.supported_methods,
            'currencies': gateway.supported_currencies,
            'fees': gateway.transaction_fees
        })


class RefundViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing refunds.
    """
    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a refund (admin only)."""
        if not request.user.is_staff:
            return Response({
                'success': False,
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        refund = self.get_object()

        if refund.status != 'pending':
            return Response({
                'success': False,
                'error': 'Refund cannot be approved'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Process refund
        refund.status = 'approved'
        refund.processed_at = timezone.now()
        refund.processed_by = request.user
        refund.admin_notes = request.data.get('admin_notes', '')
        refund.save()

        return Response({
            'success': True,
            'message': 'Refund approved successfully'
        })

    @action(detail=False, methods=['get'])
    def by_transaction(self, request):
        """Get refunds for a specific transaction."""
        transaction_id = request.query_params.get('transaction_id', None)
        if transaction_id:
            try:
                transaction = Transaction.objects.get(
                    id=transaction_id,
                    user=request.user
                )
                refunds = Refund.objects.filter(transaction=transaction)
                serializer = self.get_serializer(refunds, many=True)
                return Response(serializer.data)
            except Transaction.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Transaction not found'
                }, status=status.HTTP_404_NOT_FOUND)

        return Response({'error': 'Transaction ID parameter required'},
                      status=status.HTTP_400_BAD_REQUEST)