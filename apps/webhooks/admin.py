from django.contrib import admin

from apps.users.admin_site import admin_site

from .models import WebhookLog


class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("webhook_id", "user", "is_successful", "response_status", "created_at")
    list_filter = ("is_successful", "response_status", "created_at")
    search_fields = ("webhook_id", "user__email", "payload")


admin_site.register(WebhookLog, WebhookLogAdmin)
