"""
Users App Models - Torgovo Crypto Trading Platform
Production-ready CustomUser model with trading profile
"""

import logging
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel

logger = logging.getLogger(__name__)


# from apps.bots.models import Order


class CustomUser(AbstractUser):
    """
    Extended User model with trading-specific fields
    Integrates with all trading bots, subscriptions, and payment systems
    """

    # Override email to be unique (required because USERNAME_FIELD = 'email').
    # Django's stock AbstractUser does NOT enforce email uniqueness, which lets
    # multiple accounts share an address — a real auth-bypass risk because
    # `authenticate(username=email)` returns whichever row comes first.
    email = models.EmailField(_("email address"), unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    # Subscription Plans. FR A2 Model C slugs are DB-seeded (SubscriptionPlan
    # rows) — labels stay generic on purpose: the bot-count matrix lives on
    # the row, never hard-coded here. "enterprise" is a pre-A2 value kept so
    # existing rows stay valid.
    SUBSCRIPTION_PLAN_CHOICES = [
        ("free", _("Free")),
        ("basic", _("Basic")),
        ("standard", _("Standard")),
        ("premium", _("Premium")),
        ("creator", _("Creator")),
        ("enterprise", _("Enterprise - White label")),
    ]

    # Risk Tolerance Levels
    RISK_LEVEL_CHOICES = [
        ("conservative", _("Conservative")),
        ("moderate", _("Moderate")),
        ("aggressive", _("Aggressive")),
    ]

    # Core Trading Profile
    subscription_plan = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_PLAN_CHOICES,
        default="free",
        help_text=_("Determines max bots and feature access"),
    )

    max_bots_allowed = models.PositiveIntegerField(
        default=3, help_text=_("Maximum number of trading bots user can run")
    )

    # Trading Preferences
    demo_trading_enabled = models.BooleanField(
        default=True, help_text=_("Use demo/paper trading mode")
    )

    risk_tolerance = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default="moderate",
        help_text=_("User's risk tolerance for automated strategies"),
    )

    # Notifications
    email_notifications = models.BooleanField(
        default=True, help_text=_("Send trade notifications via email")
    )

    sms_notifications = models.BooleanField(
        default=False, help_text=_("Send trade notifications via SMS")
    )

    push_notifications = models.BooleanField(default=True, help_text=_("Send push notifications"))

    # Telegram notifications
    telegram_token = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Telegram bot token for trade notifications"),
    )
    telegram_chat_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Telegram chat ID for trade notifications"),
    )

    # Telegram channel notifications (separate from personal DM)
    channel_token = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Telegram bot token for channel broadcast notifications"),
    )
    channel_chat_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Telegram channel chat ID for broadcast notifications"),
    )

    # Trading Statistics (auto-updated)
    total_trades_executed = models.PositiveIntegerField(
        default=0, help_text=_("Total number of trades executed by all bots")
    )

    total_volume_traded = models.DecimalField(
        max_digits=20, decimal_places=8, default=0.0, help_text=_("Total trading volume in USDT")
    )

    total_profit_loss = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=0.0,
        help_text=_("Total realized P&L across all trades"),
    )

    # Exchange Integration
    default_exchange = models.ForeignKey(
        "exchanges.Exchange",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("User's preferred exchange"),
    )

    # Quantum AI Settings
    auto_compound_profits = models.BooleanField(
        default=False, help_text=_("Automatically compound Quantum AI profits")
    )

    compound_frequency = models.CharField(
        max_length=20,
        choices=[
            ("daily", _("Daily")),
            ("weekly", _("Weekly")),
            ("monthly", _("Monthly")),
        ],
        default="weekly",
        help_text=_("Quantum AI profit compounding frequency"),
    )

    # Phone / Verification
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?1?\d{9,15}$",
                message=(
                    "Phone number must be entered in the format: '+999999999'. "
                    "Up to 15 digits allowed."
                ),
            )
        ],
    )

    is_email_verified = models.BooleanField(default=False, help_text=_("Email verification status"))

    is_phone_verified = models.BooleanField(default=False, help_text=_("Phone verification status"))

    two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_(  # noqa: E501
            "Fernet-encrypted TOTP secret (see services/two_factor.py); never plaintext."
        ),
    )
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    timezone = models.CharField(
        max_length=50, default="UTC", help_text=_("User's timezone for reporting")
    )

    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customuser_referrals",  # changed from 'referrals'
    )

    # Subscription management
    subscription_start_date = models.DateTimeField(null=True, blank=True)
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    is_subscription_active = models.BooleanField(default=False)
    trading_preferences = models.JSONField(default=dict)

    # Webhook authentication token
    webhook_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text=_("Token used to authenticate webhook calls from TradingView"),
    )

    # GDPR consent tracking (COMPLIANCE Phase-1)
    # When the user accepted the Terms & Privacy Policy. NULL for accounts
    # created before consent tracking existed (grandfathered); such users must
    # re-consent before restricted actions (see compliance flows).
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the user accepted the Terms of Service and Privacy Policy"),
    )

    # Version of the Privacy Policy / Terms accepted at registration. Lets us
    # detect users whose consent was given against an older policy document.
    privacy_version = models.CharField(
        max_length=20,
        default="2026-08-1",
        help_text=_("Version of the accepted Privacy Policy/Terms (ISO date)"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_customuser"
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.username} ({self.email})"

    def save(self, *args, **kwargs):
        from core.models import SiteConfig

        if not self.referral_code:
            self.referral_code = self._generate_referral_code()

        self.max_bots_allowed = SiteConfig.get().get_plan_limit(self.subscription_plan, default=3)

        from django.db import transaction

        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.referral_code:
                from django.apps import apps

                Referral = apps.get_model("referrals", "Referral")
                # Ensure a code row exists for this referrer — but ONLY create
                # when there is none. update_or_create(referrer=self, ...) raises
                # MultipleObjectsReturned as soon as the referrer has 2+ rows
                # (one row per successful referral, A2) and would also stomp
                # status/code on event rows. exists()+create never touches rows.
                if not Referral.objects.filter(referrer=self).exists():
                    Referral.objects.create(
                        referrer=self,
                        code=self.referral_code,
                        status="pending",
                    )

    def _generate_referral_code(self):
        import secrets
        import string

        alphabet = string.ascii_uppercase + string.digits
        for _attempt in range(10):
            code = "".join(secrets.choice(alphabet) for _i in range(8))
            if not CustomUser.objects.filter(referral_code=code).exists():
                return code
        raise ValueError("Could not generate unique referral code after 10 attempts.")

    @property
    def full_name(self):
        return self.get_full_name()

    def get_full_trading_profile(self):
        """Get complete trading profile for admin/dashboard"""
        return {
            "plan": self.subscription_plan,
            "max_bots": self.max_bots_allowed,
            "demo_mode": self.demo_trading_enabled,
            "risk_level": self.risk_tolerance,
            "total_trades": self.total_trades_executed,
            "total_volume": float(self.total_volume_traded),
            "total_pnl": float(self.total_profit_loss),
            "default_exchange": self.default_exchange.name if self.default_exchange else None,
        }

    def has_active_subscription(self):
        from django.utils import timezone

        if self.subscription_plan == "free":
            return False
        if not self.is_subscription_active:
            return False
        if self.subscription_end_date and self.subscription_end_date < timezone.now():
            return False
        return True

    def can_create_more_bots(self):
        # QuantumAIBot excluded (same basis as services.plan_limits.
        # count_user_bots): it has no `user` field — rows belong to the
        # admin QuantumAIFund master fund, so a user= filter raised
        # FieldError. See docs/regression-quantum-aibot-seat-count-fielderror.md.
        from apps.bots.models import GridBot, MartingaleBot, SignalBot

        current_bot_count = (
            SignalBot.objects.filter(user=self, is_deleted=False).count()
            + GridBot.objects.filter(user=self, is_deleted=False).count()
            + MartingaleBot.objects.filter(user=self, is_deleted=False).count()
        )
        return current_bot_count < self.max_bots_allowed

    def update_trading_stats(self):
        """Recalculate trading statistics from bot data"""
        # Import inside method to avoid circular import
        from apps.investments.models import Order as InvestmentOrder

        try:
            orders = InvestmentOrder.objects.filter(user=self)
            self.total_trades_executed = orders.count()
            self.total_volume_traded = sum([o.quantity * o.price for o in orders])
            self.total_profit_loss = sum([o.profit_loss for o in orders])
            self.save()
        except Exception as e:
            logger.error("Could not update trading stats: %s", e)


class UserBalance(TimeStampedModel):
    """
    User's available balance for each currency

    Note: Uses BigAutoField id (not UUID from TimeStampedModel)
    to match the existing database schema.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="balances"
    )
    currency = models.CharField(max_length=10)  # USDT, BTC, etc.
    available = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    hold = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # Locked in orders

    class Meta:
        db_table = "users_balances"
        unique_together = ["user", "currency"]
        indexes = [models.Index(fields=["user", "currency"])]

    def __str__(self):
        return f"{self.user.email} - {self.available} {self.currency}"
