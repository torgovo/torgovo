"""
Payment and deposit models for Quantum AI system
"""
import uuid
import pytz
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from core.models import TimeStampedModel, SoftDeleteModel
from apps.exchanges.models import ExchangeCredentials

User = settings.AUTH_USER_MODEL


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
    transaction_hash = models.CharField(max_length=255, unique=True, db_index=True)
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


# ==================== NEW BOT SUBSCRIPTION MODELS ====================

class BotSubscriptionPlan(SoftDeleteModel):
    """
    Subscription plans for bot types (custom, grid, martingale, quantum_ai).
    Separate from general SubscriptionPlan.
    """

    BOT_TYPE_CHOICES = [
        ('custom', 'Custom Bot (TradingView)'),
        ('grid', 'Grid Trading Bot'),
        ('martingale', 'Martingale Bot'),
        ('quantum_ai', 'Quantum AI Fund'),
    ]

    DURATION_CHOICES = [
        (30, '30 Days'),
        (90, '90 Days'),
        (180, '180 Days'),
        (365, '365 Days'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_type = models.CharField(max_length=20, choices=BOT_TYPE_CHOICES, unique=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duration_days = models.IntegerField(choices=DURATION_CHOICES, default=30)
    description = models.TextField(blank=True)
    features = models.JSONField(default=list, help_text="List of features included")
    is_active = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments_bot_subscription_plans'
        indexes = [
            models.Index(fields=['bot_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} - ${self.price}"


class BotSubscription(SoftDeleteModel):
    """
    User's subscription to a bot service.
    Two-step flow: 1) Subscribe 2) Create bot after approval
    """

    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment Upload'),
        ('pending_approval', 'Pending Admin Approval'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bot_subscriptions')
    plan = models.ForeignKey(BotSubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment', db_index=True)

    # Payment proof
    payment_screenshot = models.ImageField(upload_to='subscriptions/payments/%Y/%m/%d/', blank=True, null=True)
    payment_transaction_hash = models.CharField(max_length=255, blank=True, help_text="For crypto payments")
    payment_blockchain = models.CharField(max_length=20, blank=True, help_text="e.g., BEP20, ERC20, TRC20")

    # Exchange selection (for custom/grid/martingale bots)
    exchange_name = models.CharField(max_length=20, choices=ExchangeCredentials.EXCHANGE_CHOICES, blank=True)

    # Admin approval fields
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_bot_subscriptions')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_bot_subscriptions')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Admin notes")

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Bot-specific fields
    webhook_secret = models.CharField(max_length=64, unique=True, blank=True, null=True, help_text="For custom bots")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments_bot_subscriptions'
        unique_together = ['user', 'plan']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['approved_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"

    @property
    def is_expired(self):
        """Check if subscription has expired"""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    def get_webhook_json_template(self):
        """Returns JSON template for TradingView (custom bots only)"""
        if not self.webhook_secret:
            return None

        return {
            "secret": self.webhook_secret,
            "exchange": self.exchange_name,
            "action": "{{strategy.order.action}}",
            "symbol": "{{ticker}}",
            "amount": "{{order.amount}}",
            "price": "{{order.price}}"
        }

    def approve(self, admin_user, notes=""):
        """
        Approve subscription and activate it.
        Creates default PairConfig for grid/martingale bots.
        """
        from apps.bots.models import PairConfig

        self.status = 'active'
        self.approved_by = admin_user
        self.approved_at = timezone.now()
        self.started_at = timezone.now()
        self.expires_at = timezone.now() + timezone.timedelta(days=self.plan.duration_days)

        # Generate webhook secret for custom bots
        if self.plan.bot_type == 'custom':
            self.webhook_secret = uuid.uuid4().hex

        self.notes = notes
        self.save()

        # Create default PairConfig for grid/martingale bots
        if self.plan.bot_type in ['grid', 'martingale']:
            PairConfig.objects.get_or_create(
                user=self.user,
                subscription=self,
                pair_symbol=f"{self.exchange_name.upper()}/USDT" if self.exchange_name else "BTC/USDT",
                bot_type=self.plan.bot_type,
                defaults={
                    'slug': f"{self.user.username}-{self.plan.bot_type}",
                    'favor_levels': 3,
                    'against_levels': 3,
                    'favor_level_qty': 0.1,
                    'against_level_qty': 0.1,
                    'favor_level_difference': 1.0,
                    'against_level_difference': 1.0,
                    'Order_Type': 'market',
                    'Amount_Type': 'dollar',
                }
            )

    def reject(self, admin_user, reason=""):
        """Reject subscription"""
        self.status = 'rejected'
        self.rejected_by = admin_user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save()