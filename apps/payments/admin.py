from django.contrib import admin
from .models import (
    SubscriptionPlan, QuantumAIDeposit, BlockchainAddress,
    WithdrawalRequest, PaymentTransaction, ReferralPayout
)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_monthly', 'max_bots_allowed', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')

@admin.register(QuantumAIDeposit)
class QuantumAIDepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'status', 'transaction_hash', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('user__email', 'transaction_hash', 'from_address')

@admin.register(BlockchainAddress)
class BlockchainAddressAdmin(admin.ModelAdmin):
    list_display = ('coin_type', 'blockchain', 'address', 'label', 'is_active', 'balance')
    list_filter = ('coin_type', 'blockchain', 'is_active', 'is_hot_wallet')
    search_fields = ('address', 'label')

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('user__email', 'to_address', 'transaction_hash')

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'currency', 'created_at')
    search_fields = ('user__email', 'reference_id', 'external_id')

@admin.register(ReferralPayout)
class ReferralPayoutAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred_user', 'amount', 'status', 'paid_at')
    list_filter = ('status', 'created_at')
    search_fields = ('referrer__email', 'referred_user__email')
