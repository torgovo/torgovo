from django import forms
from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html

from .models import BotOrder, QuantumAIFund

# ==================== ORDER INLINE ====================


class OrderInline(admin.TabularInline):
    model = BotOrder

    extra = 0
    fields = ["Pair", "Side", "Quantity", "Price", "Exchange", "Time", "Order_type", "created_at"]
    readonly_fields = ["Time", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ==================== SIGNAL BOT ADMIN ====================


class SignalBotAdmin(admin.ModelAdmin):
    inlines = [OrderInline]
    list_display = [
        "bot_name",
        "user",
        "exchange_name",
        "market_type",
        "trading_pair",
        "is_active",
        "total_trades",
        "success_rate",
    ]
    list_filter = ["exchange_name", "market_type", "is_active"]
    search_fields = ["bot_name", "user__email"]
    readonly_fields = ["webhook_url_display", "masked_secret_key", "webhook_json_template"]

    fieldsets = (
        (
            "Bot Configuration",
            {
                "fields": (
                    "bot_name",
                    "user",
                    "exchange_name",
                    "market_type",
                    "trading_pair",
                    "subscription",
                )
            },
        ),
        (
            "Trading Settings",
            {"fields": ("default_amount", "take_profit_percent", "stop_loss_percent")},
        ),
        (
            "Webhook Configuration",
            {
                "fields": ("webhook_url_display", "masked_secret_key", "webhook_json_template"),
                "classes": ("collapse",),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "total_trades",
                    "successful_trades",
                    "success_rate",
                    "total_profit_loss",
                    "signals_used_this_month",
                )
            },
        ),
    )

    def masked_secret_key(self, obj):
        if obj.secret_key and len(obj.secret_key) > 8:
            return obj.secret_key[:6] + "...****" + obj.secret_key[-4:]
        return obj.secret_key or "Not set"

    masked_secret_key.short_description = "Secret Key"

    def webhook_url_display(self, obj):
        if obj.subscription and obj.subscription.webhook_secret:
            url = f"{settings.SITE_URL}/api/webhooks/custom/{obj.user.id}/"
            return format_html('<input value="{}" readonly style="width: 100%;" />', url)
        return "No active subscription"

    def webhook_json_template(self, obj):
        if obj.subscription:
            template = obj.subscription.get_webhook_json_template()
            return format_html(
                '<pre style="background: #f4f4f4; padding: 10px;">{}</pre>', str(template)
            )
        return "No subscription"


# ==================== GRID BOT ADMIN ====================


class GridBotAdmin(admin.ModelAdmin):
    inlines = [OrderInline]
    list_display = [
        "bot_name",
        "user",
        "exchange_name",
        "trading_pair",
        "is_running",
        "current_profit_loss",
        "total_trades_executed",
    ]
    list_filter = ["exchange_name", "is_running"]
    search_fields = ["bot_name", "user__email"]
    readonly_fields = ["subscription_status"]
    actions = ["start_bot", "stop_bot"]

    fieldsets = (
        (
            "Bot Configuration",
            {"fields": ("bot_name", "user", "exchange_name", "trading_pair", "subscription")},
        ),
        (
            "Grid Settings",
            {
                "fields": (
                    "initial_amount",
                    "base_amount",
                    "favor_levels",
                    "against_levels",
                    "level_spacing_percent",
                    "favor_level_qty",
                    "against_level_qty",
                    "favor_level_difference",
                    "against_level_difference",
                    "amount_type",
                )
            },
        ),
        ("Risk Management", {"fields": ("take_profit_percent", "stop_loss_percent")}),
        ("Bot State", {"fields": ("is_running", "started_at", "stopped_at")}),
        (
            "Statistics",
            {"fields": ("current_profit_loss", "total_invested", "total_trades_executed")},
        ),
    )

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                "green" if obj.subscription.status == "active" else "red",
                obj.subscription.get_status_display(),
            )
        return "No Subscription"

    subscription_status.short_description = "Subscription Status"

    def start_bot(self, request, queryset):
        from services.bot_executor import BotExecutorService

        for bot in queryset:
            try:
                if not bot.subscription or bot.subscription.status != "active":
                    self.message_user(
                        request, f"Bot {bot.bot_name} has no active subscription", level="warning"
                    )
                    continue

                success = BotExecutorService.start_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Started {bot.bot_name}", level="success")
            except Exception as e:
                self.message_user(
                    request, f"Error starting {bot.bot_name}: {str(e)}", level="error"
                )

    start_bot.short_description = "Start Selected Bots"

    def stop_bot(self, request, queryset):
        from services.bot_executor import BotExecutorService

        for bot in queryset:
            try:
                success = BotExecutorService.stop_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Stopped {bot.bot_name}", level="success")
            except Exception as e:
                self.message_user(
                    request, f"Error stopping {bot.bot_name}: {str(e)}", level="error"
                )

    stop_bot.short_description = "Stop Selected Bots"


# ==================== MARTINGALE BOT ADMIN ====================


class MartingaleBotAdmin(admin.ModelAdmin):
    inlines = [OrderInline]
    list_display = [
        "bot_name",
        "user",
        "exchange_name",
        "trading_pair",
        "is_running",
        "current_level",
        "current_profit_loss",
    ]
    list_filter = ["exchange_name", "is_running"]
    search_fields = ["bot_name", "user__email"]
    readonly_fields = ["subscription_status"]
    actions = ["start_bot", "stop_bot"]

    fieldsets = (
        (
            "Bot Configuration",
            {"fields": ("bot_name", "user", "exchange_name", "trading_pair", "subscription")},
        ),
        (
            "Martingale Settings",
            {
                "fields": (
                    "initial_amount",
                    "base_amount",
                    "favor_levels",
                    "against_levels",
                    "level_spacing_percent",
                    "favor_level_qty",
                    "against_level_qty",
                    "favor_level_difference",
                    "against_level_difference",
                    "amount_type",
                    "multiplier_factor",
                )
            },
        ),
        ("Risk Management", {"fields": ("take_profit_percent", "stop_loss_percent")}),
        (
            "Bot State",
            {
                "fields": (
                    "is_running",
                    "current_level",
                    "max_level_reached",
                    "last_execution_price",
                    "started_at",
                    "stopped_at",
                )
            },
        ),
        (
            "Statistics",
            {"fields": ("current_profit_loss", "total_invested", "total_trades_executed")},
        ),
    )

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                "green" if obj.subscription.status == "active" else "red",
                obj.subscription.get_status_display(),
            )
        return "No Subscription"

    subscription_status.short_description = "Subscription Status"

    def start_bot(self, request, queryset):
        from services.bot_executor import BotExecutorService

        for bot in queryset:
            try:
                if not bot.subscription or bot.subscription.status != "active":
                    self.message_user(
                        request, f"Bot {bot.bot_name} has no active subscription", level="warning"
                    )
                    continue

                success = BotExecutorService.start_martingale_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Started {bot.bot_name}", level="success")
            except Exception as e:
                self.message_user(
                    request, f"Error starting {bot.bot_name}: {str(e)}", level="error"
                )

    start_bot.short_description = "Start Selected Bots"

    def stop_bot(self, request, queryset):
        from services.bot_executor import BotExecutorService

        for bot in queryset:
            try:
                success = BotExecutorService.stop_martingale_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Stopped {bot.bot_name}", level="success")
            except Exception as e:
                self.message_user(
                    request, f"Error stopping {bot.bot_name}: {str(e)}", level="error"
                )

    stop_bot.short_description = "Stop Selected Bots"


# ==================== QUANTUM AI ADMIN ====================


class QuantumAIFundForm(forms.ModelForm):
    """Custom form that masks key fields. Model-level save() auto-encrypts.

    render_value=False prevents the ciphertext from rendering in the HTML.
    required=False on the key fields lets a blank submission reach cleaned_data,
    where save_model() restores the pre-existing encrypted value.
    """

    def __init__(self, *args, **kwargs):
        """Make key fields not required so blank submissions reach cleaned_data.

        The model TextFields have blank=False by default, so Django would
        reject an empty submission before save_model() ever runs.  Making
        them not-required here lets a staff member save a fund record without
        retyping the three master secrets every time.  The save_model() guard
        on QuantumAIFundAdmin restores the existing encrypted value when the
        submitted value is blank.
        """
        super().__init__(*args, **kwargs)
        self.fields["master_api_key"].required = False
        self.fields["master_secret_key"].required = False
        self.fields["master_passphrase"].required = False

    class Meta:
        model = QuantumAIFund
        fields = "__all__"
        widgets = {
            "master_api_key": forms.PasswordInput(render_value=False),
            "master_secret_key": forms.PasswordInput(render_value=False),
            "master_passphrase": forms.PasswordInput(render_value=False),
        }
        help_texts = {
            "master_api_key": "Leave blank to keep current value.",
            "master_secret_key": "Leave blank to keep current value.",
            "master_passphrase": "Leave blank to keep current value.",
        }


class QuantumAIFundAdmin(admin.ModelAdmin):
    form = QuantumAIFundForm
    list_display = [
        "name",
        "total_fund_value",
        "total_profit",
        "total_deposits",
        "is_active",
        "last_trade_at",
    ]
    readonly_fields = ["total_profit"]
    actions = ["calculate_profit_distribution", "process_payouts"]
    list_display_links = ["name"]

    def save_model(self, request, obj, form, change):
        """Guard against blank submission wiping an existing encrypted key.

        When a key field is submitted blank (allowed by the form's
        required=False), restore the pre-existing value from the DB so
        the encrypted credential isn't silently overwritten with empty
        text.  Only applies on edits (change=True) — on creation there
        is no existing value to restore.
        """
        KEY_FIELDS = ["master_api_key", "master_secret_key", "master_passphrase"]
        if change:
            for field in KEY_FIELDS:
                if field in form.changed_data and not form.cleaned_data.get(field):
                    setattr(obj, field, QuantumAIFund.objects.get(pk=obj.pk).__dict__[field])
        super().save_model(request, obj, form, change)

    fieldsets = (
        (
            "Fund Configuration",
            {"fields": ("name", "trading_strategy", "risk_parameters", "is_active")},
        ),
        (
            "Smoothed Returns (User-Facing)",
            {
                "fields": ("monthly_min_return", "monthly_max_return", "reserve_buffer_pct"),
                "description": (
                    "Users see returns smoothed to this range. Admin absorbs loss/keeps excess."
                ),
            },
        ),
        (
            "Master API Keys",
            {
                "fields": ("master_api_key", "master_secret_key", "master_passphrase"),
                "description": (
                    "Leave blank to keep current encrypted value. Model auto-encrypts on save."
                ),
            },
        ),
        (
            "Fund Performance",
            {
                "fields": (
                    "total_fund_value",
                    "total_profit",
                    "total_deposits",
                    "last_trade_at",
                    "admin_notes",
                )
            },
        ),
    )

    def calculate_profit_distribution(self, request, queryset):
        from services.quantum_ai_fund import QuantumAIFundService  # noqa

        for fund in queryset:
            try:
                distribution = QuantumAIFundService.calculate_profit_distribution(str(fund.id))
                self.message_user(
                    request,
                    f"Calculated profit distribution for {fund.name}: "
                    f"{len(distribution)} investors",
                    level="success",
                )
            except Exception as e:
                self.message_user(request, f"Error for {fund.name}: {str(e)}", level="error")

    calculate_profit_distribution.short_description = "Calculate Profit Distribution"

    def process_payouts(self, request, queryset):
        from services.quantum_ai_fund import QuantumAIFundService  # noqa

        for fund in queryset:
            try:
                result = QuantumAIFundService.process_payouts(str(fund.id))
                self.message_user(
                    request,
                    f"Processed {result['payout_count']} payouts totaling "
                    f"${result['total_paid']:,.2f}",
                    level="success",
                )
            except Exception as e:
                self.message_user(request, f"Error processing payouts: {str(e)}", level="error")

    process_payouts.short_description = "Process Payouts to Users"


class QuantumAIBotAdmin(admin.ModelAdmin):
    list_display = [
        "bot_name",
        "fund",
        "exchange_name",
        "trading_pair",
        "is_running",
        "total_trades",
        "total_profit_loss",
        "last_trade_at",
    ]
    list_filter = ["exchange_name", "is_running", "fund"]
    search_fields = ["bot_name", "fund__name"]
    readonly_fields = ["total_trades", "total_profit_loss", "last_error"]
    actions = ["start_bot", "stop_bot"]

    fieldsets = (
        ("Bot Configuration", {"fields": ("bot_name", "fund", "exchange_name", "trading_pair")}),
        (
            "Strategy Parameters",
            {
                "fields": ("strategy_parameters",),
                "description": "Entry/Exit configs, indicator thresholds, grid levels (JSON)",
            },
        ),
        ("Bot State", {"fields": ("is_running", "started_at", "stopped_at")}),
        (
            "Performance",
            {"fields": ("total_trades", "total_profit_loss", "last_trade_at", "last_error")},
        ),
    )

    def start_bot(self, request, queryset):
        from apps.trading.engines.execution import run_bot

        for bot in queryset:
            try:
                result = run_bot(str(bot.id), bot_type="quantum_ai")
                if result.get("success"):
                    self.message_user(
                        request,
                        f"Started {bot.bot_name} — {result.get('signal', 'ok')}",
                        level="success",
                    )
                else:
                    self.message_user(
                        request,
                        f"Error starting {bot.bot_name}: {result.get('error', 'unknown')}",
                        level="error",
                    )
            except Exception as e:
                self.message_user(
                    request, f"Error starting {bot.bot_name}: {str(e)}", level="error"
                )

    start_bot.short_description = "Start Selected Quantum AI Bots"

    def stop_bot(self, request, queryset):
        from apps.trading.engines.execution import stop_bot as _stop_bot

        for bot in queryset:
            try:
                result = _stop_bot(str(bot.id), bot_type="quantum_ai")
                if result.get("success"):
                    self.message_user(request, f"Stopped {bot.bot_name}", level="success")
                else:
                    self.message_user(
                        request,
                        f"Error stopping {bot.bot_name}: {result.get('error', 'unknown')}",
                        level="error",
                    )
            except Exception as e:
                self.message_user(
                    request, f"Error stopping {bot.bot_name}: {str(e)}", level="error"
                )

    stop_bot.short_description = "Stop Selected Quantum AI Bots"


class ReserveFundAdmin(admin.ModelAdmin):
    list_display = ["fund", "balance", "is_below_target", "last_top_up", "last_withdrawal"]
    list_filter = ["fund"]
    search_fields = ["fund__name"]
    readonly_fields = ["balance", "last_top_up", "last_withdrawal", "low_balance_alert_sent"]

    fieldsets = (
        ("Reserve Info", {"fields": ("fund", "balance", "low_balance_alert_sent")}),
        ("Activity", {"fields": ("last_top_up", "last_withdrawal")}),
    )

    def is_below_target(self, obj):
        below = obj.is_below_target()
        from django.utils.html import format_html

        color = "red" if below else "green"
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            "⚠ Below Target" if below else "✅ Adequate",
        )

    is_below_target.short_description = "Reserve Status"


class InvestorPortfolioAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "fund",
        "amount",
        "share_percentage",
        "status",
        "accrued_profit",
        "total_payouts",
    ]
    list_filter = ["status", "fund"]
    search_fields = ["user__email"]
    readonly_fields = ["share_percentage"]

    fieldsets = (
        (
            "Investment Details",
            {"fields": ("user", "fund", "amount", "share_percentage", "status")},
        ),
        ("Financial Tracking", {"fields": ("accrued_profit", "total_payouts", "deposited_at")}),
    )


# ==================== INDICATOR & PAIR CONFIG ADMIN ====================


class IndicatorAdmin(admin.ModelAdmin):
    list_display = ["user", "Pair", "RSI", "Color", "BB", "created_at"]
    list_filter = ["Pair", "created_at"]
    search_fields = ["user__email", "Pair"]


class PairConfigAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "pair_symbol",
        "bot_type",
        "favor_levels",
        "against_levels",
        "Order_Type",
        "Amount_Type",
        "subscription_status",
    ]
    list_filter = ["bot_type", "Order_Type", "Amount_Type"]
    search_fields = ["user__email", "pair_symbol"]
    readonly_fields = ["slug"]

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                "green" if obj.subscription.status == "active" else "red",
                obj.subscription.get_status_display(),
            )
        return "No Subscription"

    subscription_status.short_description = "Subscription Status"


class OrderAdmin(admin.ModelAdmin):
    list_display = ["Pair", "Side", "Quantity", "Price", "Exchange", "Time"]
    list_filter = ["Side", "Exchange", "Time"]
    search_fields = ["Pair", "user__email"]


# Telegram Signals admin moved to apps/subscriptions/admin.py
