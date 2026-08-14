from django.contrib import admin

from apps.users.admin_site import admin_site

from .models import EmailVerification, LoginAttempt, PasswordResetToken, PhoneVerification


class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "is_verified", "verified_at", "expires_at")
    list_filter = ("is_verified",)
    search_fields = ("user__email",)


class PhoneVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "is_verified", "attempts", "expires_at")
    list_filter = ("is_verified",)
    search_fields = ("user__email", "phone_number")


class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "is_used", "used_at", "expires_at")
    list_filter = ("is_used",)
    search_fields = ("user__email",)


class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "ip_address", "was_successful", "created_at")
    list_filter = ("was_successful", "created_at")
    search_fields = ("username", "ip_address")


admin_site.register(EmailVerification, EmailVerificationAdmin)
admin_site.register(PhoneVerification, PhoneVerificationAdmin)
admin_site.register(PasswordResetToken, PasswordResetTokenAdmin)
admin_site.register(LoginAttempt, LoginAttemptAdmin)
