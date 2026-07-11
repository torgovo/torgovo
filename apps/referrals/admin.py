from django.contrib import admin
from .models import Referral

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred_user', 'code', 'bonus_amount', 'status', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('referrer__email', 'referred_user__email', 'code')
