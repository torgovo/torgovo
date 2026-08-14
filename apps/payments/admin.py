from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.payments.models import BotSubscription, BotSubscriptionPlan
from apps.users.admin_site import admin_site
from services.subscription_service import SubscriptionService


class BotSubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "bot_type", "price", "duration_days", "is_active"]
    list_filter = ["bot_type", "is_active"]
    search_fields = ["name"]


class BotSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "payment_proof", "approve_reject_buttons"]
    list_filter = ["status", "plan__bot_type", "exchange_name"]
    search_fields = ["user__email", "payment_transaction_hash"]
    readonly_fields = ["webhook_url_display", "webhook_json_template", "webhook_secret"]

    fieldsets = (
        ("User & Plan", {"fields": ("user", "plan", "status", "exchange_name")}),
        (
            "Payment Proof",
            {"fields": ("payment_screenshot", "payment_transaction_hash", "payment_blockchain")},
        ),
        (
            "Admin Actions",
            {
                "fields": (
                    "approved_by",
                    "approved_at",
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                    "notes",
                )
            },
        ),
        (
            "Webhook Configuration (Custom Bots)",
            {
                "fields": ("webhook_url_display", "webhook_json_template", "webhook_secret"),
                "classes": ("collapse",),
            },
        ),
    )

    def payment_proof(self, obj):
        if obj.payment_screenshot:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="height: 50px;" /></a>',
                obj.payment_screenshot.url,
                obj.payment_screenshot.url,
            )
        return "No Image"

    def webhook_url_display(self, obj):
        if obj.webhook_secret:
            url = f"{settings.SITE_URL}/api/webhooks/custom/{obj.user.id}/"
            return format_html(
                '<input type="text" value="{}" readonly style="width: 400px;" />', url
            )
        return "Not generated"

    def webhook_json_template(self, obj):
        if obj.webhook_secret:
            template = obj.get_webhook_json_template()
            return format_html(
                '<pre style="background: #f4f4f4; padding: 10px;">{}</pre>', str(template)
            )
        return "No secret"

    def approve_reject_buttons(self, obj):
        if obj.status == "pending_approval":
            approve_url = reverse("admin:approve_subscription", args=[obj.id])
            reject_url = reverse("admin:reject_subscription", args=[obj.id])
            return format_html(
                '<a class="button" href="{}" '
                'style="background: green; color: white; padding: 5px;">Approve</a> '
                '<a class="button" href="{}" '
                'style="background: red; color: white; padding: 5px;">Reject</a>',
                approve_url,
                reject_url,
            )
        return obj.get_status_display()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:subscription_id>/approve/",
                self.approve_subscription,
                name="approve_subscription",
            ),
            path(
                "<uuid:subscription_id>/reject/",
                self.reject_subscription,
                name="reject_subscription",
            ),
        ]
        return custom_urls + urls

    def approve_subscription(self, request, subscription_id):
        try:
            subscription = BotSubscription.objects.get(id=subscription_id)
            SubscriptionService.approve_subscription(str(subscription.id), request.user)
            messages.success(request, f"Approved subscription for {subscription.user.email}")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return HttpResponseRedirect(reverse("admin:payments_botsubscription_changelist"))

    def reject_subscription(self, request, subscription_id):
        if request.method == "POST":
            reason = request.POST.get("reason", "")
            try:
                SubscriptionService.reject_subscription(str(subscription_id), request.user, reason)
                messages.success(request, f"Rejected: {reason}")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
            return HttpResponseRedirect(reverse("admin:payments_botsubscription_changelist"))

        # Show rejection form
        return render(
            request, "admin/reject_subscription.html", {"subscription_id": subscription_id}
        )


admin_site.register(BotSubscriptionPlan, BotSubscriptionPlanAdmin)
admin_site.register(BotSubscription, BotSubscriptionAdmin)
