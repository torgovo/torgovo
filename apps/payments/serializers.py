"""
Serializers for payment processing models
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models

from .models import (
    PaymentMethod, Transaction, Invoice, WithdrawalRequest,
    PaymentGateway, Refund
)

User = get_user_model()


class PaymentGatewaySerializer(serializers.ModelSerializer):
    """
    Serializer for PaymentGateway model.
    """
    class Meta:
        model = PaymentGateway
        fields = [
            'id', 'name', 'gateway_type', 'is_active', 'supported_methods',
            'supported_currencies', 'transaction_fees', 'daily_limit',
            'monthly_limit', 'webhook_url', 'config'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentMethodSerializer(serializers.ModelSerializer):
    """
    Serializer for PaymentMethod model.
    """
    masked_account_number = serializers.SerializerMethodField()
    gateway_name = serializers.CharField(source='gateway.name', read_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'gateway', 'gateway_name', 'method_type', 'provider',
            'masked_account_number', 'account_holder_name', 'card_type',
            'card_last_four', 'expiry_month', 'expiry_year',
            'is_default', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at',
            'card_last_four'  # Set automatically
        ]
        extra_kwargs = {
            'gateway': {'required': True},
            'method_type': {'required': True},
            'is_default': {'default': False},
            'is_active': {'default': True}
        }

    def get_masked_account_number(self, obj):
        """Return masked account number for display."""
        if obj.account_number:
            account = obj.account_number
            if len(account) > 8:
                return f"****{account[-4:]}"
        return "****"

    def validate(self, data):
        """Validate payment method data."""
        method_type = data.get('method_type')

        # Card-specific validation
        if method_type in ['credit_card', 'debit_card']:
            required_fields = ['account_holder_name', 'expiry_month', 'expiry_year']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError(f"{field} is required for cards")

        # Bank account validation
        elif method_type == 'bank_account':
            if not data.get('account_holder_name'):
                raise serializers.ValidationError("Account holder name is required for bank accounts")

        return data

    def create(self, validated_data):
        """Create payment method with card number processing."""
        user = self.context['request'].user
        account_number = validated_data.pop('account_number', None)

        # Handle default setting
        if validated_data.get('is_default', False):
            # Unset other default payment methods of same type
            PaymentMethod.objects.filter(
                user=user,
                method_type=validated_data['method_type']
            ).update(is_default=False)

        payment_method = PaymentMethod.objects.create(
            user=user,
            **validated_data
        )

        # Set account number and extract card details
        if account_number:
            payment_method.set_account_number(account_number)
            if validated_data['method_type'] in ['credit_card', 'debit_card']:
                payment_method.set_card_details(account_number)

        payment_method.save()
        return payment_method


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for Transaction model.
    """
    payment_method_type = serializers.CharField(
        source='payment_method.method_type', read_only=True
    )
    payment_method_display = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'invoice', 'invoice_number', 'payment_method',
            'payment_method_type', 'payment_method_display',
            'transaction_id', 'transaction_type', 'amount',
            'currency', 'status', 'gateway_response', 'fee_amount',
            'exchange_rate', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'transaction_id', 'created_at', 'updated_at'
        ]

    def get_payment_method_display(self, obj):
        """Get payment method display string."""
        if obj.payment_method:
            if obj.payment_method.method_type in ['credit_card', 'debit_card']:
                return f"{obj.payment_method.get_method_type_display()} ending in {obj.payment_method.card_last_four}"
            else:
                return obj.payment_method.get_method_type_display()
        return "N/A"


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Serializer for Invoice model.
    """
    transactions = TransactionSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    amount_paid = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'user', 'amount', 'currency',
            'description', 'status', 'status_display', 'due_date',
            'paid_at', 'created_at', 'updated_at', 'transactions',
            'amount_paid'
        ]
        read_only_fields = [
            'id', 'user', 'invoice_number', 'created_at', 'updated_at',
            'paid_at'
        ]

    def get_amount_paid(self, obj):
        """Calculate amount paid for this invoice."""
        paid_transactions = obj.transactions.filter(status='completed')
        return sum(t.amount for t in paid_transactions)

    def create(self, validated_data):
        """Create invoice with automatic invoice number generation."""
        user = self.context['request'].user

        # Generate unique invoice number
        last_invoice = Invoice.objects.filter(
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month
        ).order_by('-invoice_number').first()

        if last_invoice:
            try:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1

        invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{new_num:04d}"

        return Invoice.objects.create(
            user=user,
            invoice_number=invoice_number,
            **validated_data
        )


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for WithdrawalRequest model.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_type = serializers.CharField(
        source='payment_method.method_type', read_only=True
    )

    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'user', 'amount', 'currency', 'payment_method',
            'payment_method_type', 'destination_address',
            'withdrawal_type', 'status', 'status_display',
            'transaction_hash', 'fee_amount', 'network_fee',
            'processed_at', 'cancelled_at', 'notes',
            'admin_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'processed_at', 'cancelled_at',
            'admin_notes', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'destination_address': {'required': True},
            'withdrawal_type': {'default': 'crypto'}
        }

    def validate_amount(self, value):
        """Validate withdrawal amount."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")

        # Check minimum withdrawal amount
        if value < 10:  # $10 minimum
            raise serializers.ValidationError("Minimum withdrawal amount is $10")

        return value

    def validate_payment_method(self, value):
        """Validate payment method belongs to user."""
        user = self.context['request'].user
        if value.user != user:
            raise serializers.ValidationError("Invalid payment method")

        if not value.is_active:
            raise serializers.ValidationError("Payment method is not active")

        return value

    def create(self, validated_data):
        """Create withdrawal request."""
        user = self.context['request'].user

        # Validate user has sufficient balance (this would integrate with actual balance system)
        # For now, we'll just create the request

        return WithdrawalRequest.objects.create(
            user=user,
            **validated_data
        )


class RefundSerializer(serializers.ModelSerializer):
    """
    Serializer for Refund model.
    """
    transaction_id_display = serializers.CharField(
        source='transaction.transaction_id', read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Refund
        fields = [
            'id', 'user', 'transaction', 'transaction_id_display',
            'amount', 'currency', 'reason', 'status', 'status_display',
            'refund_transaction_id', 'processed_by',
            'processed_at', 'admin_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'refund_transaction_id',
            'processed_by', 'processed_at', 'admin_notes',
            'created_at', 'updated_at'
        ]

    def validate_transaction(self, value):
        """Validate transaction belongs to user and is refundable."""
        user = self.context['request'].user

        if value.user != user:
            raise serializers.ValidationError("Invalid transaction")

        if value.status != 'completed':
            raise serializers.ValidationError("Only completed transactions can be refunded")

        # Check if refund already exists
        if Refund.objects.filter(transaction=value, status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError("Refund already exists for this transaction")

        return value

    def validate_amount(self, value):
        """Validate refund amount."""
        if value <= 0:
            raise serializers.ValidationError("Refund amount must be greater than 0")

        return value

    def create(self, validated_data):
        """Create refund request."""
        user = self.context['request'].user

        # Validate refund amount doesn't exceed transaction amount
        transaction = validated_data['transaction']
        refund_amount = validated_data['amount']

        # Check existing refunds for this transaction
        existing_refunds = Refund.objects.filter(
            transaction=transaction,
            status='approved'
        ).aggregate(total_refunded=models.Sum('amount'))['total_refunded'] or 0

        if existing_refunds + refund_amount > transaction.amount:
            raise serializers.ValidationError(
                f"Refund amount exceeds remaining refundable amount. "
                f"Remaining: ${transaction.amount - existing_refunds}"
            )

        return Refund.objects.create(
            user=user,
            **validated_data
        )


class InvoicePaymentSerializer(serializers.Serializer):
    """
    Serializer for invoice payment requests.
    """
    payment_method_id = serializers.UUIDField(required=True)

    def validate_payment_method_id(self, value):
        """Validate payment method exists and belongs to user."""
        user = self.context['request'].user

        try:
            payment_method = PaymentMethod.objects.get(
                id=value,
                user=user,
                is_active=True
            )
            return payment_method
        except PaymentMethod.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive payment method")


class DiscountCodeValidationSerializer(serializers.Serializer):
    """
    Serializer for discount code validation.
    """
    code = serializers.CharField(required=True, max_length=50)
    plan_id = serializers.UUIDField(required=False)