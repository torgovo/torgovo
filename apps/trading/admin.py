from django.contrib import admin

from apps.users.admin_site import admin_site

from .models import StrategyConfig

# Exchange, ExchangeCredentials, ExchangeStatus, TradingPair,
# SupportedBlockchain, ExchangeRate are all registered in apps/exchanges/admin.py


class StrategyConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "strategy", "is_active")
    list_filter = ("strategy", "is_active")
    search_fields = ("name", "description")


admin_site.register(StrategyConfig, StrategyConfigAdmin)
