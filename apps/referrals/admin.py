from django.contrib import admin

from apps.users.admin_site import admin_site

from .models import Referral


class ReferralAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referred_user", "code", "bonus_amount", "status", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("referrer__email", "referred_user__email", "code")


admin_site.register(Referral, ReferralAdmin)
