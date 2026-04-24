from django.contrib import admin
from .models import StrategyConfig
# Exchange, ExchangeCredentials, ExchangeStatus, TradingPair,
# SupportedBlockchain, ExchangeRate are all registered in apps/exchanges/admin.py


@admin.register(StrategyConfig)
class StrategyConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'strategy', 'is_active')
    list_filter = ('strategy', 'is_active')
    search_fields = ('name', 'description')
