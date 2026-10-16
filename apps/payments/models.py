"""
Payment and deposit models for Quantum AI system
"""

import logging
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.exchanges.models import ExchangeCredentials
from core.models import SoftDeleteModel, TimeStampedModel

User = settings.AUTH_USER_MODEL

logger = logging.getLogger(__name__)


class SubscriptionPlan(TimeStampedModel):
    """
    Subscription plans for different service tiers.

    G1 (FR A2): plans are fully admin-driven — every price/limit lives in
    DB rows editable from the admin. Nothing about plan tiers may be
    hard-coded in application code. ``sort_order`` (not price) controls
    display order so tiers stay in the canonical Free→Creator ladder.
    """

    MARKET_CHOICES = [
        ("spot", "Spot only"),
        ("spot_futures", "Spot + Futures"),
    ]

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=255, blank=True)
    price_monthly = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    price_yearly = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    sort_order = models.PositiveIntegerField(default=100)
    max_bots_allowed = models.PositiveIntegerField()
    max_webhooks_allowed = models.PositiveIntegerField(default=10)
    # FR A2 free-tier limits (admin-editable; paid values seeded as
    # placeholders — TBD until approved, see migration 0009)
    bot_types = models.JSONField(default=list, blank=True)
    market = models.CharField(max_length=20, choices=MARKET_CHOICES, default="spot")
    max_signals_per_month = models.PositiveIntegerField(default=10)
    max_exchanges = models.PositiveIntegerField(default=1)
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    stripe_price_id = models.CharField(max_length=100, blank=True)
    trial_days = models.PositiveIntegerField(default=0)
    # G5 / FR A7 referral commission tier ladder: holders of a plan with this
    # flag earn cash commissions on their referees' payments (seeded:
    # creator=True in migration 0013; admin-editable, no code constants).
    grants_referral_commission = models.BooleanField(default=False)

    class Meta:
        db_table = "payments_subscription_plans"
        ordering = ["sort_order", "price_monthly"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} (${self.price_monthly}/month)"

    @property
    def annual_discount_pct(self):
        """Derived annual saving vs paying monthly (0 for free plans).

        Coerces via str() so both Decimal (post-refresh) and float
        (pre-refresh instance attrs) work without TypeError.
        """
        monthly = Decimal(str(self.price_monthly or 0))
        yearly = Decimal(str(self.price_yearly or 0))
        if monthly <= 0 or yearly <= 0:
            return 0
        full_year = monthly * 12
        return int(round((Decimal(1) - (yearly / full_year)) * 100))

    @property
    def feature_dict(self):
        """Return features as dict with defaults"""
        if isinstance(self.features, dict):
            return self.features
        return {
            "max_bots": self.max_bots_allowed,
            "webhook_alerts": self.max_webhooks_allowed,
            "include_quantum_ai": False,
            "priority_support": False,
            "advanced_analytics": False,
            "max_positions": 50,
        }


class InvestorDeposit(SoftDeleteModel):  # Original name: QuantumAIDeposit (renamed for clarity)
    """
    Enhanced deposit model for Quantum AI bot funding.
    """

    STATUS_CHOICES = [
        ("pending", "Pending Verification"),
        ("processing", "Processing"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments_quantum_deposits"
    )
    quantum_bot = models.ForeignKey(
        "bots.QuantumAIBot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quantum_deposits",
    )
    fund = models.ForeignKey(
        "bots.QuantumAIFund",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_deposits",
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[MinValueValidator(Decimal("0.00000001"))]
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
        upload_to="quantum_deposits/screenshots/%Y/%m/%d/", blank=True, null=True
    )
    transaction_proof = models.FileField(
        upload_to="quantum_deposits/proofs/%Y/%m/%d/", blank=True, null=True
    )

    # Status and verification
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    admin_notes = models.TextField(blank=True)

    # Verification tracking
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_deposits",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_method = models.CharField(
        max_length=20,
        choices=[
            ("manual", "Manual Review"),
            ("automatic", "Automatic"),
            ("blockchain", "Blockchain API"),
        ],
        default="manual",
    )

    # Amount after conversion (if currency != USDT)
    usdt_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Risk scoring
    risk_score = models.IntegerField(default=0, help_text="0-100, higher = more risky")
    flagged_for_review = models.BooleanField(default=False)

    class Meta:
        db_table = "payments_quantum_deposits"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["fund", "status"]),
            models.Index(fields=["transaction_hash"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["flagged_for_review"]),
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

        self.status = "approved"
        self.verified_by = verified_by_user
        self.verified_at = timezone.now()
        self.admin_notes = notes
        self.save()

        # Update quantum bot total deposited
        try:
            if hasattr(self, "quantum_bot"):
                self.quantum_bot.total_deposited += self.usdt_amount or self.amount
                self.quantum_bot.save()
        except Exception as e:
            # Don't swallow signals (KeyboardInterrupt etc.); narrow to
            # Exception only.
            logger.warning(f"Quantum bot total_deposited update failed: {e!r}")

        # Log the approval
        from core.models import AuditLog

        AuditLog.objects.create(
            user=verified_by_user,
            action="deposit_approved",
            resource_type="InvestorDeposit",
            resource_id=str(self.id),
            new_values={"status": "approved", "usdt_amount": str(self.usdt_amount)},
            description=f"Approved deposit of {self.amount} {self.currency} from {self.user.email}",
        )

    def reject(self, verified_by_user, reason=""):
        """Reject the deposit."""
        from django.utils import timezone

        self.status = "rejected"
        self.verified_by = verified_by_user
        self.verified_at = timezone.now()
        self.admin_notes = reason
        self.save()

        # Log the rejection
        from core.models import AuditLog

        AuditLog.objects.create(
            user=verified_by_user,
            action="deposit_rejected",
            resource_type="InvestorDeposit",
            resource_id=str(self.id),
            new_values={"status": "rejected", "reason": reason},
            description=(
                f"Rejected deposit of {self.amount} {self.currency} "
                f"from {self.user.email}: {reason}"
            ),
        )


class BlockchainAddress(TimeStampedModel):
    """
    Blockchain addresses for receiving cryptocurrency deposits.
    """

    COIN_TYPES = [
        ("USDT", "Tether"),
        ("USDC", "USD Coin"),
        ("BTC", "Bitcoin"),
        ("ETH", "Ethereum"),
        ("BNB", "Binance Coin"),
        ("MATIC", "Polygon"),
        ("SOL", "Solana"),
        ("ADA", "Cardano"),
        ("DOT", "Polkadot"),
    ]

    coin_type = models.CharField(max_length=10, choices=COIN_TYPES)
    blockchain = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_hot_wallet = models.BooleanField(
        default=False, help_text="Hot wallet for frequent withdrawals"
    )
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    # Security settings
    requires_multisig = models.BooleanField(default=False)
    min_confirmations = models.PositiveIntegerField(default=6)
    max_daily_limit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    class Meta:
        db_table = "payments_blockchain_addresses"
        unique_together = ["coin_type", "blockchain", "address"]
        indexes = [
            models.Index(fields=["coin_type", "blockchain"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_hot_wallet"]),
        ]

    def __str__(self):
        return f"{self.coin_type} on {self.blockchain}: {self.address[:10]}..."


class WithdrawalRequest(SoftDeleteModel):
    """
    Withdrawal requests for user funds.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawal_requests"
    )
    amount = models.DecimalField(
        max_digits=20, decimal_places=8, validators=[MinValueValidator(Decimal("0.00000001"))]
    )
    currency = models.CharField(max_length=10)
    blockchain = models.CharField(max_length=20)
    to_address = models.CharField(max_length=255)
    transaction_hash = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    # Fees and processing
    network_fee = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    processing_fee = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    total_amount = models.DecimalField(max_digits=20, decimal_places=8)

    # Verification (two_factor_code removed — SEC-2: was dead weight.
    # The actual TOTP verification uses CustomUser.totp_secret via
    # services/two_factor.py. The serializer still accepts the field
    # for API compatibility; views pop it before save.)
    email_verification_token = models.CharField(max_length=64, blank=True)
    admin_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_withdrawals",
    )
    admin_notes = models.TextField(blank=True)

    # Security
    risk_score = models.IntegerField(default=0)
    flagged_for_review = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "payments_withdrawal_requests"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["currency"]),
            models.Index(fields=["flagged_for_review"]),
        ]

    def __str__(self):
        return f"Withdrawal: {self.amount} {self.currency} - {self.user.email}"


class PaymentTransaction(TimeStampedModel):
    """
    General payment transaction records.
    """

    TRANSACTION_TYPES = [
        ("deposit", "Deposit"),
        ("withdrawal", "Withdrawal"),
        ("subscription", "Subscription"),
        ("refund", "Refund"),
        ("fee", "Fee"),
        # G5: cash commission paid out to a referrer (linked from
        # ReferralPayoutRequest.payment_transaction)
        ("referral_payout", "Referral payout"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_transactions"
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    currency = models.CharField(max_length=10)
    reference_id = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(max_length=100, blank=True)
    gateway = models.CharField(max_length=50, default="system")
    status = models.CharField(max_length=20, default="pending")
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "payment_transactions"
        indexes = [
            models.Index(fields=["user", "transaction_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} {self.currency} - {self.user.email}"


class ReferralPayout(SoftDeleteModel):
    """ "
    Referral commission payouts.
    """

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_payouts"
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referred_payouts"
    )
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    source_transaction = models.ForeignKey(
        PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_referral_payouts"
        indexes = [
            models.Index(fields=["referrer", "status"]),
            models.Index(fields=["referred_user"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Referral: {self.amount} - {self.referrer.email}"


class ReferralPayoutRequest(SoftDeleteModel):
    """G5 / FR A7: referrer requests a cash payout of accrued commissions.

    Flow (mirrors quantum withdrawal requests): the user asks for
    `amount_requested` (USD, must be >= admin-configured payout_minimum_usd
    and <= their pending ReferralPayout balance). An admin then pays the
    referrer in crypto/fiat OUTSIDE the platform, enters the actual
    `admin_entered_payout` (covering network fees) and decides. On approve,
    FIFO-slices the pending ReferralPayout rows covering `amount_requested`
    to paid and books one `referral_payout` PaymentTransaction for the
    admin-entered amount; on reject the accruals stay pending untouched.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_payout_requests",
    )
    amount_requested = models.DecimalField(max_digits=20, decimal_places=8)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )

    # Decision fields (admin)
    admin_entered_payout = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Actual amount paid out to the referrer, incl. fees",
    )
    admin_notes = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_referral_payout_requests",
    )
    # Ledger bookkeeping: the referral_payout PaymentTransaction created at
    # approval (null until then).
    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_payout_requests",
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments_referral_payout_requests"
        ordering = ["-requested_at"]
        constraints = [
            # G5 race guard: at most ONE pending request per user. The service
            # checks exists() but two concurrent POSTs could both pass without
            # this DB-level constraint.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="pending"),
                name="uniq_pending_payout_request_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "-requested_at"]),
        ]

    def __str__(self):
        return f"Payout {self.amount_requested} by {self.user.email} [{self.status}]"


# ==================== NEW BOT SUBSCRIPTION MODELS ====================


class BotSubscriptionPlan(SoftDeleteModel):
    """ "
    Subscription plans for bot types (custom, grid, martingale, quantum_ai).
    Separate from general SubscriptionPlan.
    """

    BOT_TYPE_CHOICES = [
        ("custom", "Custom Bot (TradingView)"),
        ("grid", "Grid Trading Bot"),
        ("martingale", "Martingale Bot"),
        ("quantum_ai", "Quantum AI Fund"),
    ]

    DURATION_CHOICES = [
        (30, "30 Days"),
        (90, "90 Days"),
        (180, "180 Days"),
        (365, "365 Days"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # unique removed (G5): the Model C tier ladder needs one "custom" shim
    # plan per tier (Free/Basic/Standard/Premium/Creator) — bot_type is a
    # coarse type discriminator only. Regression doc: see docs/
    # regression-bot-type-unique-drop.md
    bot_type = models.CharField(max_length=20, choices=BOT_TYPE_CHOICES)
    name = models.CharField(max_length=100)
    # G5 tier bridge: which Model C SubscriptionPlan tier this bot plan
    # belongs to (null for pure per-bot plans like grid/martingale). The
    # referral commission tier check walks BotSubscription -> plan ->
    # subscription_plan.
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_subscription_plans",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duration_days = models.IntegerField(choices=DURATION_CHOICES, default=30)
    description = models.TextField(blank=True)
    features = models.JSONField(default=list, help_text="List of features included")
    is_active = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments_bot_subscription_plans"
        indexes = [
            models.Index(fields=["bot_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} - ${self.price}"


class BotSubscription(SoftDeleteModel):
    """ "
    User's subscription to a bot service.
    Two-step flow: 1) Subscribe 2) Create bot after approval
    """

    STATUS_CHOICES = [
        ("pending_payment", "Pending Payment Upload"),
        ("pending_approval", "Pending Admin Approval"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bot_subscriptions")
    plan = models.ForeignKey(
        BotSubscriptionPlan, on_delete=models.CASCADE, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending_payment", db_index=True
    )

    # Payment proof
    payment_screenshot = models.ImageField(
        upload_to="subscriptions/payments/%Y/%m/%d/", blank=True, null=True
    )
    payment_transaction_hash = models.CharField(
        max_length=255, blank=True, help_text="For crypto payments"
    )
    payment_blockchain = models.CharField(
        max_length=20, blank=True, help_text="e.g., BEP20, ERC20, TRC20"
    )

    # Exchange selection (for custom/grid/martingale bots)
    exchange_name = models.CharField(
        max_length=20, choices=ExchangeCredentials.EXCHANGE_CHOICES, blank=True
    )

    # G5 / FR A7 referee discount (first subscription payment only):
    # discount_applied = percent taken (e.g. 15.00 = 15% off, null = none);
    # amount_due = net payable after the discount (null = full plan price).
    # amount_due is also the commission accrual basis when set (payment-code
    # fulfill copies the already-discounted fiat_amount here).
    discount_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Referee discount percent applied at subscribe (FR A7); null = none",
    )
    amount_due = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Net payable after referee discount; null = full plan price",
    )

    # Admin approval fields
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_bot_subscriptions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_bot_subscriptions",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Admin notes")

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # G4 / FR A6 expiry lifecycle:
    # grace_until = end of the 2-day (configurable) grace window AFTER
    # expires_at during which the user keeps FULL access; after it the
    # subscription is hard-stopped (no new bot entries).
    grace_until = models.DateTimeField(
        null=True, blank=True, help_text="End of post-expiry grace window (FR A6)"
    )
    # Idempotency ledger for expiry reminder emails: {"D-7": "<ISO ts>", ...}.
    # Keys reset on every approve() so each paid term re-arms its reminders.
    expiry_reminders_sent = models.JSONField(
        default=dict, blank=True, help_text="Offsets already emailed this term (e.g. D-7)"
    )

    # Bot-specific fields
    webhook_secret = models.CharField(
        max_length=64, unique=True, blank=True, null=True, help_text="For custom bots"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments_bot_subscriptions"
        unique_together = ["user", "plan"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["approved_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"

    def approve(self, approved_by, notes=""):
        """Approve (or re-approve after expiry) and start the paid clock.

        G4 / FR A6: approval now stamps started_at and derives expires_at
        from plan.duration_days. Grace window = expires_at + the
        admin-configured SUBSCRIPTION_GRACE_PERIOD_DAYS. Reminder ledger is
        cleared so the new term re-arms D-7/5/3/1 emails. Re-approving an
        expired row restores access while RETAINING all bot rows (they keep
        their FK to this same subscription — A6 "retained data").
        """
        now = timezone.now()
        duration_days = getattr(self.plan, "duration_days", None) or 30
        grace_days = getattr(settings, "SUBSCRIPTION_GRACE_PERIOD_DAYS", 2)

        self.status = "active"
        self.approved_by = approved_by
        self.approved_at = now
        self.started_at = now
        self.expires_at = now + timezone.timedelta(days=duration_days)
        self.grace_until = self.expires_at + timezone.timedelta(days=grace_days)
        self.expiry_reminders_sent = {}
        self.notes = notes
        self.save()

    def reject(self, admin_user, reason):
        self.status = "rejected"
        self.rejection_reason = reason
        self.rejected_by = admin_user
        self.rejected_at = timezone.now()
        self.save()

    @property
    def is_expired(self):
        """Check if subscription has expired"""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    def get_webhook_json_template(self):
        """Return TradingView-compatible webhook JSON template."""
        return {
            "subscription_id": str(self.id),
            "secret": self.webhook_secret or "",
            "Pair": "{{syminfo.basecurrency}}/{{syminfo.currency}}",
            "position_size": "{{strategy.position_size}}",
            "exchange": self.exchange_name or "binance",
            "timestamp": "{{timenow}}",
            "side": "{{strategy.order.action}}",
            "order_id": "{{strategy.order.id}}",
            "price": "{{close}}",
        }


# ============================================================================
# G2 / FR A3 — MANUAL MULTI-COIN PAYMENTS: coin list, payment code, quote
# ----------------------------------------------------------------------------
# Domain split (deliberate): BlockchainAddress (above) is WITHDRAWAL-side
# (hot wallets, balances, confirmations). PaymentCoin below is RECEIVE-side
# config for plan payments only — lean on purpose, seeded by
# `manage.py seed_payment_coins`, addresses left blank until admin sets the
# real on-chain deposit addresses.
# ============================================================================


class PaymentCoin(TimeStampedModel):
    """
    Admin-configurable coin/chain list for receiving plan payments (FR A3).

    Launch set (seeded): USDT on TRC20, BEP20, ERC20.
    `deposit_address` starts blank — the seed never invents addresses;
    code creation fails with a clear 400 until admin sets a real address.
    """

    coin = models.CharField(max_length=10)  # e.g. USDT — free text, not choice-locked
    chain = models.CharField(max_length=20)  # e.g. TRC20 / BEP20 / ERC20
    deposit_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="On-chain receive address. Empty = not configured yet.",
    )
    memo = models.CharField(
        max_length=100, blank=True, help_text="Tag/memo if the chain requires one"
    )
    min_amount = models.DecimalField(
        max_digits=20, decimal_places=8, default=0, validators=[MinValueValidator(0)]
    )
    # Per-chain buffer covering network fees, in COIN units (e.g. 0.20 USDT).
    # Included in the quote's combined payable amount (plan price + this fee).
    # Seeded at 0 — the seed never invents values; admin sets real buffers.
    network_fee = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Chain fee buffer in coin units, added to plan price in quotes",
    )
    # Admin-configurable payment-window length (FR A3: default 6 hours).
    # After this expires the user must explicitly re-request a quote.
    quote_window_seconds = models.PositiveIntegerField(
        default=21600,
        help_text="How long a payment window stays open (seconds) before re-request is required",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=10)

    class Meta:
        db_table = "payments_payment_coins"
        unique_together = ["coin", "chain"]
        ordering = ["sort_order", "coin", "chain"]

    def __str__(self):
        return f"{self.coin} on {self.chain}"

    @property
    def is_configured(self):
        """Address must be set by an admin before quotes can point at it."""
        return bool(self.deposit_address)


class PaymentCode(TimeStampedModel):
    """
    Unique per-order payment handle (FR A3 step 1).

    Created when the user picks a plan; carries the frozen fiat amount.
    The crypto amount lives on PaymentQuote rows (price re-locks while the
    code is still `awaiting_payment`; frozen at proof submission).
    """

    ORDER_KIND_CHOICES = [
        ("telegram_signal", "Telegram Signal Plan"),
        ("bot", "Bot Subscription Plan"),
    ]
    STATUS_CHOICES = [
        ("awaiting_payment", "Awaiting Payment"),
        ("submitted", "Proof Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    code = models.CharField(max_length=12, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_codes")
    order_kind = models.CharField(max_length=20, choices=ORDER_KIND_CHOICES)
    # Exactly one of the two plan FKs is set, matching order_kind.
    telegram_plan = models.ForeignKey(
        "subscriptions.TelegramSignalPlan",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_codes",
    )
    bot_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_codes",
    )
    billing_cycle = models.CharField(max_length=16, default="monthly")
    fiat_amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    # G5 / FR A7: referee discount percent baked into fiat_amount at code
    # creation (null = full price); copied onto the subscription at fulfill.
    discount_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Referee discount percent applied to fiat_amount (FR A7); null = none",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="awaiting_payment", db_index=True
    )
    # Polymorphic pointer to the subscription created at proof time
    # (TelegramSubscription or BotSubscription — order_kind disambiguates).
    subscription_id = models.CharField(max_length=36, blank=True)
    # Frozen rate/crypto amount at proof submission (audit for admin verify).
    locked_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    locked_crypto_amount = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )
    locked_coin = models.CharField(max_length=10, blank=True)
    # End of the open payment window (FR A3): set at the first quote,
    # reset only by an explicit re-request. While open, TTL-expired polls
    # re-lock automatically; once past, the quote stays expired until the
    # user re-requests (no silent re-lock at the then-current price).
    quote_window_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_payment_codes"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        """Unambiguous uppercase code (no 0/O/1/I) — readable off a screen."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(10))
            if not PaymentCode.objects.filter(code=code).exists():
                return code

    def __str__(self):
        return f"{self.code} ({self.get_status_display()})"

    @property
    def plan(self):
        """The resolved plan object for this code's order kind."""
        return self.telegram_plan if self.order_kind == "telegram_signal" else self.bot_plan

    @property
    def current_quote(self):
        """Latest quote row (the live price lock, if any)."""
        return self.quotes.order_by("-locked_at").first()


class PaymentQuote(TimeStampedModel):
    """
    One price-lock event for a PaymentCode (FR A3 step 2).

    Short refresh cadence (default 300s = 5 minutes — FE auto-updates the
    combined amount while the payment window is open). The row's expires_at
    is truncated at the payment window end, so `is_expired` flips exactly
    when re-request becomes required. `crypto_amount` is the combined
    payable amount (plan price + per-chain fee buffer). History is kept for
    audit; at proof submission the latest quote is frozen onto locked_*.
    """

    code = models.ForeignKey(PaymentCode, on_delete=models.CASCADE, related_name="quotes")
    coin = models.ForeignKey(PaymentCoin, on_delete=models.PROTECT, related_name="quotes")
    fiat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    rate = models.DecimalField(max_digits=18, decimal_places=8, help_text="USD per 1 unit of coin")
    crypto_amount = models.DecimalField(max_digits=20, decimal_places=8)
    locked_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "payments_payment_quotes"
        ordering = ["-locked_at"]
        indexes = [
            models.Index(fields=["code", "locked_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.crypto_amount} {self.coin.coin} @ {self.rate} ({self.code.code})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
