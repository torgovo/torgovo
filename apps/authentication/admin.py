from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser, UserProfile, EmailVerification,
    PhoneVerification, PasswordResetToken, LoginAttempt
)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'phone_number', 'is_phone_verified', 'is_email_verified', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('email',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription_plan', 'is_subscription_active', 'total_trades_executed')
    list_filter = ('subscription_plan', 'is_subscription_active')
    search_fields = ('user__email', 'referral_code')

@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_verified', 'verified_at', 'expires_at')
    list_filter = ('is_verified',)
    search_fields = ('user__email',)

@admin.register(PhoneVerification)
class PhoneVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'is_verified', 'attempts', 'expires_at')
    list_filter = ('is_verified',)
    search_fields = ('user__email', 'phone_number')

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_used', 'used_at', 'expires_at')
    list_filter = ('is_used',)
    search_fields = ('user__email',)

@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip_address', 'was_successful', 'created_at')
    list_filter = ('was_successful', 'created_at')
    search_fields = ('username', 'ip_address')