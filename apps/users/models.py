"""
Users App Models - Torgovo Crypto Trading Platform
Production-ready CustomUser model with trading profile
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_extensions.db.models import TimeStampedModel


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
    email = models.EmailField(_('email address'), unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    # Subscription Plans (matching your business logic)
    SUBSCRIPTION_PLAN_CHOICES = [
        ('free', _('Free - 3 bots max')),
        ('basic', _('Basic - 10 bots max')),
        ('premium', _('Premium - Unlimited bots')),
        ('enterprise', _('Enterprise - White label')),
    ]

    # Risk Tolerance Levels
    RISK_LEVEL_CHOICES = [
        ('conservative', _('Conservative')),
        ('moderate', _('Moderate')),
        ('aggressive', _('Aggressive')),
    ]

    # Core Trading Profile
    subscription_plan = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_PLAN_CHOICES,
        default='free',
        help_text=_("Determines max bots and feature access")
    )

    max_bots_allowed = models.PositiveIntegerField(
        default=3,
        help_text=_("Maximum number of trading bots user can run")
    )

    # Trading Preferences
    demo_trading_enabled = models.BooleanField(
        default=True,
        help_text=_("Use demo/paper trading mode")
    )

    risk_tolerance = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default='moderate',
        help_text=_("User's risk tolerance for automated strategies")
    )

    # Notifications
    email_notifications = models.BooleanField(
        default=True,
        help_text=_("Send trade notifications via email")
    )

    sms_notifications = models.BooleanField(
        default=False,
        help_text=_("Send trade notifications via SMS")
    )

    push_notifications = models.BooleanField(
        default=True,
        help_text=_("Send push notifications")
    )

    # Trading Statistics (auto-updated)
    total_trades_executed = models.PositiveIntegerField(
        default=0,
        help_text=_("Total number of trades executed by all bots")
    )

    total_volume_traded = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=0.0,
        help_text=_("Total trading volume in USDT")
    )

    total_profit_loss = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=0.0,
        help_text=_("Total realized P&L across all trades")
    )

    # Exchange Integration
    default_exchange = models.ForeignKey(
        'exchanges.Exchange',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("User's preferred exchange")
    )

    # Quantum AI Settings
    auto_compound_profits = models.BooleanField(
        default=False,
        help_text=_("Automatically compound Quantum AI profits")
    )

    compound_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', _('Daily')),
            ('weekly', _('Weekly')),
            ('monthly', _('Monthly')),
        ],
        default='weekly',
        help_text=_("Quantum AI profit compounding frequency")
    )

    # Phone / Verification
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
            )
        ]
    )

    is_email_verified = models.BooleanField(
        default=False,
        help_text=_("Email verification status")
    )

    is_phone_verified = models.BooleanField(
        default=False,
        help_text=_("Phone verification status")
    )

    two_factor_enabled = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text=_("User's timezone for reporting")
    )

    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customuser_referrals'   # changed from 'referrals'
    )

    # Webhook authentication token
    webhook_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text=_("Token used to authenticate webhook calls from TradingView"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_customuser'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.username} ({self.email})"

    def save(self, *args, **kwargs):
        # Auto-update max_bots_allowed based on subscription plan
        plan_limits = {
            'free': 3,
            'basic': 10,
            'premium': 999999,  # Unlimited
            'enterprise': 999999,
        }
        self.max_bots_allowed = plan_limits.get(self.subscription_plan, 3)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.get_full_name()

    def get_full_trading_profile(self):
        """Get complete trading profile for admin/dashboard"""
        return {
            'plan': self.subscription_plan,
            'max_bots': self.max_bots_allowed,
            'demo_mode': self.demo_trading_enabled,
            'risk_level': self.risk_tolerance,
            'total_trades': self.total_trades_executed,
            'total_volume': float(self.total_volume_traded),
            'total_pnl': float(self.total_profit_loss),
            'default_exchange': self.default_exchange.name if self.default_exchange else None,
        }

    def update_trading_stats(self):
        """Recalculate trading statistics from bot data"""
        # Import inside method to avoid circular import
        from apps.bots.models import Order

        try:
            orders = Order.objects.filter(user=self)
            self.total_trades_executed = orders.count()
            self.total_volume_traded = sum([o.quantity * o.price for o in orders])
            self.total_profit_loss = sum([o.profit_loss for o in orders])
            self.save()
        except Exception as e:
            print(f"Could not update trading stats: {e}")


class UserBalance(TimeStampedModel):
    """
    User's available balance for each currency
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='balances')
    currency = models.CharField(max_length=10)  # USDT, BTC, etc.
    available = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    hold = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # Locked in orders

    class Meta:
        db_table = 'users_balances'
        unique_together = ['user', 'currency']
        indexes = [models.Index(fields=['user', 'currency'])]

    def __str__(self):
        return f"{self.user.email} - {self.available} {self.currency}"
