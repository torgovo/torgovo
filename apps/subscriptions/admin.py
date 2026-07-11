from django.contrib import admin
from .models import (
    TelegramSignalPlan, TelegramChannel, TelegramSubscription,
    TradingSignal, SignalResult, SignalStatistics
)

@admin.register(TelegramSignalPlan)
class TelegramSignalPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_monthly', 'risk_level', 'is_active')
    list_filter = ('risk_level', 'is_active')
    search_fields = ('name',)

@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'channel_id', 'channel_type', 'member_count', 'is_active')
    list_filter = ('channel_type', 'is_active')
    search_fields = ('name', 'channel_id')

@admin.register(TelegramSubscription)
class TelegramSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'end_date', 'telegram_handle')
    list_filter = ('status', 'plan', 'billing_cycle')
    search_fields = ('user__email', 'telegram_handle')

@admin.register(TradingSignal)
class TradingSignalAdmin(admin.ModelAdmin):
    list_display = ('signal_type', 'trading_pair', 'plan', 'published_at', 'is_active')
    list_filter = ('signal_type', 'is_active', 'plan')
    search_fields = ('trading_pair', 'analysis')

@admin.register(SignalResult)
class SignalResultAdmin(admin.ModelAdmin):
    list_display = ('signal', 'result_type', 'profit_loss_percent', 'exit_time')
    list_filter = ('result_type',)

@admin.register(SignalStatistics)
class SignalStatisticsAdmin(admin.ModelAdmin):
    list_display = ('plan', 'date', 'total_signals', 'win_rate', 'total_profit_loss')
    list_filter = ('plan', 'date')
