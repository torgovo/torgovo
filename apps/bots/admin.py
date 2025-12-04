from django.contrib import admin
from .models import (
    WebhookAlert, GridBot, MartingaleBot, QuantumAIBot,
    Indicator, PairConfig, Order, TechnicalIndicator,
    Signal, RunningThreads
)

@admin.register(WebhookAlert)
class WebhookAlertAdmin(admin.ModelAdmin):
    list_display = ('bot_name', 'user', 'exchange_name', 'trading_pair', 'is_active', 'total_trades', 'total_profit_loss')
    list_filter = ('exchange_name', 'is_active', 'created_at')
    search_fields = ('bot_name', 'user__email', 'trading_pair')

@admin.register(GridBot)
class GridBotAdmin(admin.ModelAdmin):
    list_display = ('bot_name', 'user', 'exchange_name', 'trading_pair', 'is_running', 'current_profit_loss')
    list_filter = ('exchange_name', 'is_running', 'created_at')
    search_fields = ('bot_name', 'user__email', 'trading_pair')

@admin.register(MartingaleBot)
class MartingaleBotAdmin(admin.ModelAdmin):
    list_display = ('bot_name', 'user', 'exchange_name', 'trading_pair', 'is_running', 'current_profit_loss')
    list_filter = ('exchange_name', 'is_running', 'created_at')
    search_fields = ('bot_name', 'user__email', 'trading_pair')

@admin.register(QuantumAIBot)
class QuantumAIBotAdmin(admin.ModelAdmin):
    list_display = ('bot_name', 'user', 'risk_level', 'total_deposited', 'current_profit_loss', 'is_active')
    list_filter = ('risk_level', 'is_active', 'created_at')
    search_fields = ('bot_name', 'user__email')

@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('Pair', 'user', 'RSI', 'created_at')
    list_filter = ('Pair', 'created_at')
    search_fields = ('user__email', 'Pair')

@admin.register(PairConfig)
class PairConfigAdmin(admin.ModelAdmin):
    list_display = ('slug', 'pair_symbol', 'user', 'Order_Type', 'created_at')
    list_filter = ('Order_Type', 'created_at')
    search_fields = ('slug', 'pair_symbol', 'user__email')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('Pair', 'Side', 'Quantity', 'Price', 'status', 'user', 'Time')
    list_filter = ('Side', 'status', 'Exchange', 'Time')
    search_fields = ('Pair', 'user__email', 'id')

@admin.register(TechnicalIndicator)
class TechnicalIndicatorAdmin(admin.ModelAdmin):
    list_display = ('indicator_type', 'pair', 'exchange', 'timeframe', 'value', 'timestamp')
    list_filter = ('indicator_type', 'exchange', 'timeframe')
    search_fields = ('pair',)

@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ('indicator1', 'indicator2', 'created_at')
    list_filter = ('created_at',)

@admin.register(RunningThreads)
class RunningThreadsAdmin(admin.ModelAdmin):
    list_display = ('thread_id', 'created_at')
