from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'subscription_plan', 'is_active', 'date_joined', 'last_login']
    list_filter = ['subscription_plan', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Trading Profile', {
            'fields': ('subscription_plan', 'max_bots_allowed', 'demo_trading_enabled', 
                      'email_notifications', 'sms_notifications')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Trading Profile', {
            'fields': ('subscription_plan', 'max_bots_allowed', 'demo_trading_enabled')
        }),
    )
    
    readonly_fields = ['date_joined', 'last_login']
