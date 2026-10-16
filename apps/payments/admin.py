from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.payments.models import (
    BotSubscription,
    BotSubscriptionPlan,
    PaymentCode,
    PaymentCoin,
    SubscriptionPlan,
)
from apps.users.admin_site import admin_site
from services.subscription_service import SubscriptionService


class BotSubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "bot_type", "price", "duration_days", "is_active"]
    list_filter = ["bot_type", "is_active"]
    search_fields = ["name"]


class SubscriptionPlanAdmin(admin.ModelAdmin):
    """
    G1 / FR A2: full admin surface for Model C plans.

    Every price and limit below is DB-driven — editing a row here
    immediately changes the plans API (cache is invalidated by
    payments.signals) and therefore every client. Do NOT move any of
    these values into code constants.
    """

    list_display = [
        "sort_order",
        "name",
        "slug",
        "price_monthly",
        "price_yearly",
        "annual_discount_display",
        "market",
        "max_bots_allowed",
        "max_signals_per_month",
        "is_active",
    ]
    list_editable = ["price_monthly", "price_yearly", "sort_order"]
    list_display_links = ("name",)
    list_filter = ["is_active", "market"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["annual_discount_pct"]
    ordering = ["sort_order", "price_monthly"]

    fieldsets = (
        (
            "Tier",
            {
                "fields": ("name", "slug", "description", "sort_order", "is_active", "trial_days"),
                "description": (
                    "Model C ladder: Free / Basic / Standard / Premium / Creator (FR A2)."
                ),
            },
        ),
        (
            "Pricing (admin-driven, USD)",
            {
                "fields": ("price_monthly", "price_yearly", "annual_discount_pct"),
                "description": (
                    "Set both prices directly; annual discount % is derived. "
                    "Locked Model C reference: Free 0, Basic 15, Standard 25, "
                    "Premium 49, Creator 20 (monthly)."
                ),
            },
        ),
        (
            "Limits (FR A2)",
            {
                "fields": (
                    "bot_types",
                    "market",
                    "max_signals_per_month",
                    "max_exchanges",
                    "max_bots_allowed",
                    "max_webhooks_allowed",
                ),
                "description": (
                    "Free (locked): bot_types ['signal'], spot only, 10 signals/mo, "
                    "1 exchange, 1 bot. Paid-tier values are placeholders until "
                    "approved — set them here (TBD, FR A2)."
                ),
            },
        ),
        ("Features (JSON extras)", {"fields": ("features", "stripe_price_id")}),
    )

    @admin.display(description="Annual % off")
    def annual_discount_display(self, obj):
        return f"{obj.annual_discount_pct}%"


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
admin_site.register(SubscriptionPlan, SubscriptionPlanAdmin)


class PaymentCoinAdmin(admin.ModelAdmin):
    """
    G2 / FR A3: admin-configured receive list. Set the real on-chain
    deposit_address here — the seed never invents addresses, and quote
    creation 400s until an address exists for the chosen coin.

    `network_fee` (per-chain buffer in coin units) and
    `quote_window_seconds` (default 6h) are also admin-configurable and
    seeded at defaults only — no invented values.
    """

    list_display = [
        "coin",
        "chain",
        "deposit_address_set",
        "network_fee",
        "quote_window_seconds",
        "min_amount",
        "is_active",
        "sort_order",
    ]
    list_editable = ["is_active", "sort_order"]
    list_filter = ["coin", "chain", "is_active"]
    search_fields = ["coin", "chain", "deposit_address"]
    ordering = ["sort_order", "coin"]

    @admin.display(description="Address configured")
    def deposit_address_set(self, obj):
        return "yes" if obj.deposit_address else "NO (set it!)"


class PaymentCodeAdmin(admin.ModelAdmin):
    """
    G2 / FR A3: read-only audit surface for payment codes.

    The approve/reject decision happens on the linked SUBSCRIPTION
    (existing admin flows) — sync_payment_code_status mirrors it back onto
    this row. status here is manually overridable as a break-glass only.
    """

    list_display = [
        "code",
        "user",
        "order_kind",
        "fiat_amount",
        "status",
        "locked_crypto_display",
        "created_at",
    ]
    list_filter = ["status", "order_kind", "locked_coin"]
    search_fields = ["code", "user__email", "subscription_id"]
    readonly_fields = [
        "code",
        "user",
        "order_kind",
        "telegram_plan",
        "bot_plan",
        "billing_cycle",
        "fiat_amount",
        "subscription_id",
        "locked_rate",
        "locked_crypto_amount",
        "locked_coin",
        "quote_window_expires_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    @admin.display(description="Locked crypto")
    def locked_crypto_display(self, obj):
        if obj.locked_crypto_amount:
            return f"{obj.locked_crypto_amount} {obj.locked_coin}"
        return "—"


admin_site.register(PaymentCoin, PaymentCoinAdmin)
admin_site.register(PaymentCode, PaymentCodeAdmin)
