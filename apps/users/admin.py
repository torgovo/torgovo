from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.admin_site import admin_site
from core.models import AuditLog, UserActivityLog

from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "subscription_plan",
        "is_active",
        "date_joined",
        "last_login",
    ]
    list_filter = ["subscription_plan", "is_active", "is_staff", "date_joined"]
    search_fields = ["username", "email", "first_name", "last_name"]

    fieldsets = UserAdmin.fieldsets + (
        (
            "Trading Profile",
            {
                "fields": (
                    "subscription_plan",
                    "max_bots_allowed",
                    "demo_trading_enabled",
                    "email_notifications",
                    "sms_notifications",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Trading Profile",
            {"fields": ("subscription_plan", "max_bots_allowed", "demo_trading_enabled")},
        ),
    )

    readonly_fields = ["date_joined", "last_login"]


admin_site.register(CustomUser, CustomUserAdmin)


@admin.register(UserActivityLog, site=admin_site)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ["user", "action", "created_at", "ip_address"]
    list_filter = ["action", "created_at"]
    search_fields = ["user__email", "action", "description"]
    readonly_fields = [
        "user",
        "action",
        "description",
        "ip_address",
        "user_agent",
        "endpoint",
        "method",
        "status_code",
        "created_at",
    ]
    date_hierarchy = "created_at"


@admin.register(AuditLog, site=admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "resource_type", "resource_id", "user", "created_at"]
    list_filter = ["action", "resource_type", "created_at"]
    search_fields = ["user__email", "resource_type", "resource_id", "description"]
    readonly_fields = [
        "user",
        "action",
        "resource_type",
        "resource_id",
        "old_values",
        "new_values",
        "description",
        "ip_address",
        "user_agent",
        "created_at",
    ]
    date_hierarchy = "created_at"
