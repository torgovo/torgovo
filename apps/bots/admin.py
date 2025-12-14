from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django.utils import timezone
from .models import (
    CustomBot, GridBot, MartingaleBot,
    QuantumAIFund, QuantumAIInvestment,
    Indicator, PairConfig, Order,
    TelegramSignalPlan, TelegramSignalSubscription
)


# ==================== CUSTOM BOT ADMIN ====================

@admin.register(CustomBot)
class CustomBotAdmin(admin.ModelAdmin):
    list_display = [
        'bot_name', 'user', 'exchange_name', 'market_type',
        'trading_pair', 'is_active', 'total_trades', 'success_rate'
    ]
    list_filter = ['exchange_name', 'market_type', 'is_active']
    search_fields = ['bot_name', 'user__email']
    readonly_fields = ['webhook_url_display', 'secret_key', 'webhook_json_template']

    fieldsets = (
        ('Bot Configuration', {
            'fields': ('bot_name', 'user', 'exchange_name', 'market_type', 'trading_pair', 'subscription')
        }),
        ('Trading Settings', {
            'fields': ('default_amount', 'take_profit_percent', 'stop_loss_percent')
        }),
        ('Webhook Configuration', {
            'fields': ('webhook_url_display', 'secret_key', 'webhook_json_template'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_trades', 'successful_trades', 'success_rate', 'total_profit_loss', 'signals_used_this_month')
        }),
    )

    def webhook_url_display(self, obj):
        if obj.subscription and obj.subscription.webhook_secret:
            url = f"{settings.SITE_URL}/api/webhooks/custom/{obj.user.id}/"
            return format_html('<input value="{}" readonly style="width: 100%;" />', url)
        return "No active subscription"

    def webhook_json_template(self, obj):
        if obj.subscription:
            template = obj.subscription.get_webhook_json_template()
            return format_html('<pre style="background: #f4f4f4; padding: 10px;">{}</pre>', str(template))
        return "No subscription"


# ==================== GRID BOT ADMIN ====================

@admin.register(GridBot)
class GridBotAdmin(admin.ModelAdmin):
    list_display = [
        'bot_name', 'user', 'exchange_name', 'trading_pair',
        'is_running', 'current_profit_loss', 'total_trades_executed'
    ]
    list_filter = ['exchange_name', 'is_running']
    search_fields = ['bot_name', 'user__email']
    readonly_fields = ['subscription_status']
    actions = ['start_bot', 'stop_bot']

    fieldsets = (
        ('Bot Configuration', {
            'fields': ('bot_name', 'user', 'exchange_name', 'trading_pair', 'subscription')
        }),
        ('Grid Settings', {
            'fields': (
                'initial_amount', 'base_amount', 'favor_levels', 'against_levels',
                'level_spacing_percent', 'favor_level_qty', 'against_level_qty',
                'favor_level_difference', 'against_level_difference', 'amount_type'
            )
        }),
        ('Risk Management', {
            'fields': ('take_profit_percent', 'stop_loss_percent')
        }),
        ('Bot State', {
            'fields': ('is_running', 'started_at', 'stopped_at')
        }),
        ('Statistics', {
            'fields': ('current_profit_loss', 'total_invested', 'total_trades_executed')
        }),
    )

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                'green' if obj.subscription.status == 'active' else 'red',
                obj.subscription.get_status_display()
            )
        return "No Subscription"

    subscription_status.short_description = 'Subscription Status'

    def start_bot(self, request, queryset):
        from services.bot_executor_service import BotExecutorService

        for bot in queryset:
            try:
                if not bot.subscription or bot.subscription.status != 'active':
                    self.message_user(request, f"Bot {bot.bot_name} has no active subscription", level='warning')
                    continue

                success = BotExecutorService.start_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Started {bot.bot_name}", level='success')
            except Exception as e:
                self.message_user(request, f"Error starting {bot.bot_name}: {str(e)}", level='error')

    start_bot.short_description = "Start Selected Bots"

    def stop_bot(self, request, queryset):
        for bot in queryset:
            try:
                success = BotExecutorService.stop_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Stopped {bot.bot_name}", level='success')
            except Exception as e:
                self.message_user(request, f"Error stopping {bot.bot_name}: {str(e)}", level='error')

    stop_bot.short_description = "Stop Selected Bots"


# ==================== MARTINGALE BOT ADMIN ====================

@admin.register(MartingaleBot)
class MartingaleBotAdmin(admin.ModelAdmin):
    list_display = [
        'bot_name', 'user', 'exchange_name', 'trading_pair',
        'is_running', 'current_level', 'current_profit_loss'
    ]
    list_filter = ['exchange_name', 'is_running']
    search_fields = ['bot_name', 'user__email']
    readonly_fields = ['subscription_status']
    actions = ['start_bot', 'stop_bot']

    fieldsets = (
        ('Bot Configuration', {
            'fields': ('bot_name', 'user', 'exchange_name', 'trading_pair', 'subscription')
        }),
        ('Martingale Settings', {
            'fields': (
                'initial_amount', 'base_amount', 'favor_levels', 'against_levels',
                'level_spacing_percent', 'favor_level_qty', 'against_level_qty',
                'favor_level_difference', 'against_level_difference', 'amount_type',
                'multiplier_factor'
            )
        }),
        ('Risk Management', {
            'fields': ('take_profit_percent', 'stop_loss_percent')
        }),
        ('Bot State', {
            'fields': ('is_running', 'current_level', 'max_level_reached', 'last_execution_price', 'started_at', 'stopped_at')
        }),
        ('Statistics', {
            'fields': ('current_profit_loss', 'total_invested', 'total_trades_executed')
        }),
    )

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                'green' if obj.subscription.status == 'active' else 'red',
                obj.subscription.get_status_display()
            )
        return "No Subscription"

    subscription_status.short_description = 'Subscription Status'

    def start_bot(self, request, queryset):
        from services.bot_executor_service import BotExecutorService

        for bot in queryset:
            try:
                if not bot.subscription or bot.subscription.status != 'active':
                    self.message_user(request, f"Bot {bot.bot_name} has no active subscription", level='warning')
                    continue

                success = BotExecutorService.start_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Started {bot.bot_name}", level='success')
            except Exception as e:
                self.message_user(request, f"Error starting {bot.bot_name}: {str(e)}", level='error')

    start_bot.short_description = "Start Selected Bots"

    def stop_bot(self, request, queryset):
        for bot in queryset:
            try:
                success = BotExecutorService.stop_grid_bot(request.user, str(bot.id))
                if success:
                    self.message_user(request, f"Stopped {bot.bot_name}", level='success')
            except Exception as e:
                self.message_user(request, f"Error stopping {bot.bot_name}: {str(e)}", level='error')

    stop_bot.short_description = "Stop Selected Bots"


# ==================== QUANTUM AI ADMIN ====================

@admin.register(QuantumAIFund)
class QuantumAIFundAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'total_fund_value', 'total_profit',
        'total_deposits', 'is_active', 'last_trade_at'
    ]
    readonly_fields = ['total_profit']
    actions = ['calculate_profit_distribution', 'process_payouts']

    fieldsets = (
        ('Fund Configuration', {
            'fields': ('name', 'trading_strategy', 'risk_parameters', 'is_active')
        }),
        ('Master API Keys', {
            'fields': ('master_api_key', 'master_secret_key', 'master_passphrase'),
            'description': 'WARNING: These are encrypted at rest but visible to admins'
        }),
        ('Fund Performance', {
            'fields': (
                'total_fund_value', 'total_profit', 'total_deposits',
                'last_trade_at', 'admin_notes'
            )
        }),
    )

    def calculate_profit_distribution(self, request, queryset):
        from services.quantum_ai_fund import QuantumAIFundService

        for fund in queryset:
            try:
                distribution = QuantumAIFundService.calculate_profit_distribution(str(fund.id))
                self.message_user(
                    request,
                    f"Calculated profit distribution for {fund.name}: {len(distribution)} investors",
                    level='success'
                )
            except Exception as e:
                self.message_user(request, f"Error for {fund.name}: {str(e)}", level='error')

    calculate_profit_distribution.short_description = "Calculate Profit Distribution"

    def process_payouts(self, request, queryset):
        from services.quantum_ai_fund import QuantumAIFundService

        for fund in queryset:
            try:
                result = QuantumAIFundService.process_payouts(str(fund.id))
                self.message_user(
                    request,
                    f"Processed {result['payout_count']} payouts totaling ${result['total_paid']:,.2f}",
                    level='success'
                )
            except Exception as e:
                self.message_user(request, f"Error processing payouts: {str(e)}", level='error')

    process_payouts.short_description = "Process Payouts to Users"


@admin.register(QuantumAIInvestment)
class QuantumAIInvestmentAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'fund', 'amount', 'share_percentage',
        'status', 'accrued_profit', 'total_payouts'
    ]
    list_filter = ['status', 'fund']
    search_fields = ['user__email']
    readonly_fields = ['share_percentage']

    fieldsets = (
        ('Investment Details', {
            'fields': ('user', 'fund', 'amount', 'share_percentage', 'status')
        }),
        ('Financial Tracking', {
            'fields': ('accrued_profit', 'total_payouts', 'deposited_at')
        }),
    )


# ==================== INDICATOR & PAIR CONFIG ADMIN ====================

@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ['user', 'Pair', 'RSI', 'Color', 'BB', 'created_at']
    list_filter = ['Pair', 'created_at']
    search_fields = ['user__email', 'Pair']


@admin.register(PairConfig)
class PairConfigAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'pair_symbol', 'bot_type', 'favor_levels', 'against_levels',
        'Order_Type', 'Amount_Type', 'subscription_status'
    ]
    list_filter = ['bot_type', 'Order_Type', 'Amount_Type']
    search_fields = ['user__email', 'pair_symbol']
    readonly_fields = ['slug']

    def subscription_status(self, obj):
        if obj.subscription:
            return format_html(
                '<span style="color: {};">{}</span>',
                'green' if obj.subscription.status == 'active' else 'red',
                obj.subscription.get_status_display()
            )
        return "No Subscription"

    subscription_status.short_description = 'Subscription Status'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['Pair', 'Side', 'Quantity', 'Price', 'Exchange', 'Time']
    list_filter = ['Side', 'Exchange', 'Time']
    search_fields = ['Pair', 'user__email']


# ==================== TELEGRAM SIGNALS ADMIN ====================

@admin.register(TelegramSignalPlan)
class TelegramSignalPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration_days', 'price_usd', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(TelegramSignalSubscription)
class TelegramSignalSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'telegram_handle', 'plan', 'status', 'expires_at']
    list_filter = ['status', 'plan']
    search_fields = ['user__email', 'telegram_handle']
    readonly_fields = ['subscribed_at', 'approved_at']