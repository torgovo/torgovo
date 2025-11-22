"""
Admin configuration for authentication models
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    CustomUser, UserProfile, EmailVerification,
    PhoneVerification, PasswordResetToken, LoginAttempt
)


@admin.register(CustomUser)
class UserAdmin(BaseUserAdmin):
    """Custom user admin."""
    list_display = (
        'email', 'username', 'first_name', 'last_name',
        'is_active', 'is_staff', 'is_email_verified',
        'is_phone_verified', 'date_joined'
    )
    list_filter = (
        'is_active', 'is_staff', 'is_superuser',
        'is_email_verified', 'is_phone_verified',
        'date_joined', 'last_login'
    )
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {
            'fields': ('first_name', 'last_name', 'email', 'phone_number')
        }),
        (_('Verification'), {
            'fields': (
                'is_email_verified', 'is_phone_verified',
                'two_factor_enabled', 'two_factor_secret'
            )
        }),
        (_('Permissions'), {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'groups', 'user_permissions'
            ),
        }),
        (_('Important dates'), {
            'fields': ('last_login', 'date_joined')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'first_name', 'last_name'
            ),
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """User profile admin."""
    list_display = (
        'user', 'subscription_plan', 'max_bots_allowed',
        'demo_trading_enabled', 'is_subscription_active',
        'created_at'
    )
    list_filter = (
        'subscription_plan', 'demo_trading_enabled',
        'is_subscription_active', 'email_notifications',
        'sms_notifications', 'push_notifications'
    )
    search_fields = ('user__email', 'user__username', 'referral_code')
    readonly_fields = ('created_at', 'updated_at', 'referral_code')

    fieldsets = (
        (None, {
            'fields': (
                'user', 'subscription_plan', 'referral_code',
                'referred_by'
            )
        }),
        (_('Bot Configuration'), {
            'fields': (
                'max_bots_allowed', 'demo_trading_enabled',
                'trading_preferences'
            )
        }),
        (_('Notifications'), {
            'fields': (
                'email_notifications', 'sms_notifications',
                'push_notifications'
            )
        }),
        (_('Subscription'), {
            'fields': (
                'subscription_start_date', 'subscription_end_date',
                'is_subscription_active'
            )
        }),
        (_('Usage Statistics'), {
            'fields': (
                'total_trades_executed', 'total_volume_traded'
            ),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    """Email verification admin."""
    list_display = ('user', 'is_verified', 'verified_at', 'expires_at', 'created_at')
    list_filter = ('is_verified', 'created_at', 'expires_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {
            'fields': ('user', 'token', 'is_verified')
        }),
        (_('Timestamps'), {
            'fields': ('verified_at', 'expires_at', 'created_at')
        }),
    )


@admin.register(PhoneVerification)
class PhoneVerificationAdmin(admin.ModelAdmin):
    """Phone verification admin."""
    list_display = (
        'user', 'phone_number', 'is_verified', 'attempts',
        'max_attempts', 'expires_at', 'created_at'
    )
    list_filter = ('is_verified', 'created_at', 'expires_at')
    search_fields = ('user__email', 'phone_number')
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {
            'fields': ('user', 'phone_number', 'code', 'is_verified')
        }),
        (_('Security'), {
            'fields': ('attempts', 'max_attempts', 'expires_at')
        }),
        (_('Timestamps'), {
            'fields': ('verified_at', 'created_at')
        }),
    )


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Password reset token admin."""
    list_display = ('user', 'is_used', 'used_at', 'expires_at', 'created_at')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {
            'fields': ('user', 'token', 'is_used')
        }),
        (_('Timestamps'), {
            'fields': ('used_at', 'expires_at', 'created_at')
        }),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Login attempt admin."""
    list_display = (
        'username', 'ip_address', 'was_successful',
        'failure_reason', 'created_at'
    )
    list_filter = ('was_successful', 'created_at', 'failure_reason')
    search_fields = ('username', 'ip_address')
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {
            'fields': ('username', 'ip_address', 'was_successful')
        }),
        (_('Details'), {
            'fields': ('user_agent', 'failure_reason')
        }),
        (_('Timestamp'), {
            'fields': ('created_at',)
        }),
    )

    def has_add_permission(self, request):
        """Disable adding login attempts manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable changing login attempts."""
        return False