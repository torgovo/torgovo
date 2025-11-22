"""
Payment and deposit models for Quantum AI system
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import TimeStampedModel, SoftDeleteModel


class SubscriptionPlan(TimeStampedModel):
    """
    Subscription plans for different service tiers.
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    price_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    price_yearly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    max_bots_allowed = models.PositiveIntegerField()
    max_webhooks_allowed = models.PositiveIntegerField(default=10)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    stripe_price_id = models.CharField(max_length=100, blank=True)
    trial_days = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'payments_subscription_plans'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} (${self.price_monthly}/month)"


class QuantumAIDeposit(SoftDeleteModel):
    """
    Enhanced deposit model for Quantum AI bot funding.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quantum_deposits'
    )
    quantum_bot = models.ForeignKey(
        'bots.QuantumAIBot',
        on_delete=models.CASCADE,
        related_name='deposits'
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    currency = models.CharField(max_length=10)
    blockchain = models.CharField(max_length=20)
    from_address = models.CharField(max_length=255)
    transaction_hash = models.CharField(max_length=255, unique=True)
    block_number = models.BigIntegerField(null=True, blank=True)
    block_confirmations = models.PositiveIntegerField(default=0)
    required_confirmations = models.PositiveIntegerField(default=6)

    # File attachments
    transaction_screenshot = models.ImageField(
        upload_to='quantum_deposits/screenshots/%Y/%m/%d/',
        blank=True,
        null=True
    )
    transaction_proof = models.FileField(
        upload_to='quantum_deposits/proofs/%Y/%m/%d/',
        blank=True,
        null=True
    )

    # Status and verification
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True)

    # Verification tracking
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_deposits'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_method = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manual Review'),
            ('automatic', 'Automatic'),
            ('blockchain', 'Blockchain API'),
        ],
        default='manual'
    )

    # Amount after conversion (if currency != USDT)
    usdt_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Risk scoring
    risk_score = models.IntegerField(default=0, help_text="0-100, higher = more risky")
    flagged_for_review = models.BooleanField(default=False)

    class Meta:
        db_table = 'payments_quantum_deposits'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['quantum_bot', 'status']),
            models.Index(fields=['transaction_hash']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['flagged_for_review']),
        ]

    def __str__(self):
        return f"{self.amount} {self.currency} - {self.user.email} ({self.status})"

    @property
    def is_expired(self):
        """Check if deposit has expired (48 hours)."""
        from django.utils import timezone
        expiry_time = self.created_at + timezone.timedelta(hours=48)
        return timezone.now() > expiry_time

    def approve(self, verified_by_user, notes=""):
        """Approve the deposit."""
        from django.utils import timezone

        self.status = 'approved'
        self.verified_by = verified_by_user
        self.verified_at = timezone.now()
        self.admin_notes = notes
        self.save()

        # Update quantum bot total deposited
        self.quantum_bot.total_deposited += self.usdt_amount or self.amount
        self.quantum_bot.save()

        # Log the approval
        from core.models import AuditLog
        AuditLog.objects.create(
            user=verified_by_user,
            action='deposit_approved',
            resource_type='QuantumAIDeposit',
            resource_id=str(self.id),
            new_values={'status': 'approved', 'usdt_amount': str(self.usdt_amount)},
            description=f"Approved deposit of {self.amount} {self.currency} from {self.user.email}"
        )

    def reject(self, verified_by_user, reason=""):
        """Reject the deposit."""
        from django.utils import timezone

        self.status = 'rejected'
        self.verified_by = verified_by_user
        self.verified_at = timezone.now()
        self.admin_notes = reason
        self.save()

        # Log the rejection
        from core.models import AuditLog
        AuditLog.objects.create(
            user=verified_by_user,
            action='deposit_rejected',
            resource_type='QuantumAIDeposit',
            resource_id=str(self.id),
            new_values={'status': 'rejected', 'reason': reason},
            description=f"Rejected deposit of {self.amount} {self.currency} from {self.user.email}: {reason}"
        )


class BlockchainAddress(TimeStampedModel):
    """
    Blockchain addresses for receiving cryptocurrency deposits.
    """
    COIN_TYPES = [
        ('USDT', 'Tether'),
        ('USDC', 'USD Coin'),
        ('BTC', 'Bitcoin'),
        ('ETH', 'Ethereum'),
        ('BNB', 'Binance Coin'),
        ('MATIC', 'Polygon'),
        ('SOL', 'Solana'),
        ('ADA', 'Cardano'),
        ('DOT', 'Polkadot'),
    ]

    coin_type = models.CharField(max_length=10, choices=COIN_TYPES)
    blockchain = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_hot_wallet = models.BooleanField(default=False, help_text="Hot wallet for frequent withdrawals")
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    # Security settings
    requires_multisig = models.BooleanField(default=False)
    min_confirmations = models.PositiveIntegerField(default=6)
    max_daily_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    class Meta:
        db_table = 'payments_blockchain_addresses'
        unique_together = ['coin_type', 'blockchain', 'address']
        indexes = [
            models.Index(fields=['coin_type', 'blockchain']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_hot_wallet']),
        ]

    def __str__(self):
        return f"{self.coin_type} on {self.blockchain}: {self.address[:10]}..."


class WithdrawalRequest(SoftDeleteModel):
    """
    Withdrawal requests for user funds.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawal_requests'
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))]
    )
    currency = models.CharField(max_length=10)
    blockchain = models.CharField(max_length=20)
    to_address = models.CharField(max_length=255)
    transaction_hash = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Fees and processing
    network_fee = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    processing_fee = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    total_amount = models.DecimalField(max_digits=20, decimal_places=8)

    # Verification
    two_factor_code = models.CharField(max_length=6, blank=True)
    email_verification_token = models.CharField(max_length=64, blank=True)
    admin_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_withdrawals'
    )
    admin_notes = models.TextField(blank=True)

    # Security
    risk_score = models.IntegerField(default=0)
    flagged_for_review = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'payments_withdrawal_requests'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['currency']),
            models.Index(fields=['flagged_for_review']),
        ]

    def __str__(self):
        return f"Withdrawal: {self.amount} {self.currency} - {self.user.email}"


class PaymentTransaction(TimeStampedModel):
    """
    General payment transaction records.
    """
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('subscription', 'Subscription'),
        ('refund', 'Refund'),
        ('fee', 'Fee'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    currency = models.CharField(max_length=10)
    reference_id = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(max_length=100, blank=True)
    gateway = models.CharField(max_length=50, default='system')
    status = models.CharField(max_length=20, default='pending')
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'payment_transactions'
        indexes = [
            models.Index(fields=['user', 'transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} {self.currency} - {self.user.email}"


class ReferralPayout(SoftDeleteModel):
    """
    Referral commission payouts.
    """
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_payouts'
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referred_payouts'
    )
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    source_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payments_referral_payouts'
        indexes = [
            models.Index(fields=['referrer', 'status']),
            models.Index(fields=['referred_user']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Referral: {self.amount} - {self.referrer.email}"