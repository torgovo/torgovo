from django.contrib import admin
from .models import (
    Exchange, ExchangeCredentials, ExchangeStatus, TradingPair,
    SupportedBlockchain, ExchangeRate
)

@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_name', 'is_active', 'supports_testnet')
    list_filter = ('is_active', 'supports_testnet')
    search_fields = ('name', 'display_name')


@admin.register(ExchangeCredentials)
class ExchangeCredentialsAdmin(admin.ModelAdmin):
    list_display = ('user', 'exchange_name', 'is_active', 'verification_status', 'trading_enabled')
    list_filter = ('exchange_name', 'is_active', 'verification_status')
    search_fields = ('user__email', 'exchange_name')

@admin.register(ExchangeStatus)
class ExchangeStatusAdmin(admin.ModelAdmin):
    list_display = ('exchange_name', 'status', 'response_time_ms', 'last_check')
    list_filter = ('status', 'exchange_name')

@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'exchange_name', 'base_asset', 'quote_asset', 'is_active')
    list_filter = ('exchange_name', 'is_active')
    search_fields = ('symbol', 'base_asset', 'quote_asset')

@admin.register(SupportedBlockchain)
class SupportedBlockchainAdmin(admin.ModelAdmin):
    list_display = ('name', 'blockchain_code', 'native_coin', 'is_active')
    list_filter = ('is_active', 'transaction_fee_type')
    search_fields = ('name', 'blockchain_code')

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate', 'exchange_name', 'timestamp')
    list_filter = ('exchange_name', 'timestamp')
    search_fields = ('from_currency', 'to_currency')
