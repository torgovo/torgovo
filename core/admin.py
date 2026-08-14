from django.contrib import admin

from .models import SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False  # singleton — only one row

    def has_delete_permission(self, request, obj=None):
        return False
