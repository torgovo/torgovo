"""
Views for Telegram signals subscription management

A9 — canonical plan-endpoint map (two models, three shapes; report §3.6):

| Endpoint | Auth | Model | Shape |
|---|---|---|---|
| /api/subscriptions/telegram/plans/ | AllowAny | TelegramSignalPlan | flat ``plans[]``, cached |
| /api/subscriptions/bot-plans/ | AllowAny | payments.SubscriptionPlan | flat ``plans[]``, cached |
| /api/subscriptions/plans/ (router) | IsAuthenticated | TelegramSignalPlan | paginated envelope |
| /api/subscriptions/public/plans/ | AllowAny | TelegramSignalPlan | paginated envelope |
"""

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.subscriptions.models import (
    SignalResult,
    TelegramChannel,
    TelegramSignalPlan,
    TelegramSubscription,
    TradingSignal,
)
from core.exceptions import Conflict


def _active_plan_ids(user):
    """A12: plan ids the user can currently read signals/results for.

    A subscription counts when its status is ``active`` AND it is not
    past ``end_date`` (null ``end_date`` on an active row = open-ended).
    Executed as a subquery — callers pass this straight into ``__in``.
    """
    today = timezone.localdate()
    return (
        TelegramSubscription.objects.filter(user=user, status="active")
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .values_list("plan_id", flat=True)
    )


def _resolve_plan(model, value):
    """A5: resolve a plan from either a primary key or a slug.

    ``telegram/subscribe`` historically matched only a numeric/UUID pk and
    ``bot-subscribe`` only a slug — sending the other form returned 400 and
    the frontend had to branch per endpoint.  Both lookup forms are accepted
    here so the payload param stays ``plan_id`` (no FE rename needed) while
    either value works on either endpoint.  Inactive plans resolve to
    ``None`` → the endpoints keep their 400 "Invalid plan_id".
    """
    value = str(value).strip()
    if not value:
        return None
    for lookup in ({"pk": value}, {"slug": value}):
        try:
            return model.objects.get(is_active=True, **lookup)
        except (model.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            continue  # pk parse failure / not found → try the other form
    return None


# Simple serializers for the viewsets
class TelegramSignalPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramSignalPlan
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "success_rate", "is_active"]


class TelegramChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChannel
        fields = "__all__"
        # All write fields on a channel are admin-only; this serializer is
        # used by a ReadOnly viewset for regular users.
        read_only_fields = ["id", "created_at", "updated_at"]


class TelegramSubscriptionSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = TelegramSubscription
        fields = "__all__"
        # SECURITY: status, approval, billing, payment fields and dates are
        # server-controlled. Plan stays writable so users can pick a plan;
        # payment proof fields stay writable for first submission (enforced
        # by the write-once gate in TelegramSubscriptionViewSet.update).
        # A11: channels M2M, billing/payment metadata, admin notes and
        # soft-delete flags are NOT user-writable — channels are assigned
        # server-side in TelegramSubscription.approve() per required_plan_id.
        read_only_fields = [
            "id",
            "user",
            "status",
            "start_date",
            "end_date",
            "signals_received",
            "last_signal_date",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "amount_paid",
            "created_at",
            "updated_at",
            # --- A11: sensitive fields previously user-writable ---
            "telegram_user_id",
            "channels",
            "billing_cycle",
            "payment_method",
            "stripe_subscription_id",
            "auto_renew",
            "success_rate_tracked",
            "rejection_reason",
            "admin_notes",
            "started_at",
            "is_deleted",
            "deleted_at",
        ]


class TradingSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingSignal
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class SignalResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalResult
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class TelegramSignalPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Telegram signal plans
    """

    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer
    permission_classes = [IsAuthenticated]


class TelegramSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user Telegram subscriptions
    """

    queryset = TelegramSubscription.objects.all()
    serializer_class = TelegramSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    PROOF_FIELDS = [
        "payment_transaction_hash",
        "payment_screenshot",
        "payment_blockchain",
    ]

    def get_queryset(self):
        return TelegramSubscription.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def update(self, request, *args, **kwargs):
        """Write-once guard for plan and payment proof fields.

        A4: the record is editable while still ``pending_payment`` (proof
        submission) AND while ``pending_approval`` (admin has not decided
        yet — typos/late proof correction are still legitimate).  Once the
        admin approves/rejects (or the row is active/expired/cancelled) the
        record is frozen.  These restrictions prevent fraud: a user cannot
        get approved on a cheap plan and switch post-approval, or alter
        submitted proof after admin review.

        A6: plan and proof checks are value-aware, not presence-based:
        resubmitting the identical value is a no-op and must not 400
        (frontend idempotent PATCH), while any *change* to a submitted
        value is rejected.  First proof submission is allowed.
        """
        instance = self.get_object()

        # --- A4: status gate — editable until an admin decision exists ---
        if instance.status not in ("pending_payment", "pending_approval"):
            raise serializers.ValidationError("This subscription can no longer be edited.")

        # --- A6: plan is write-once BY VALUE (identical value = no-op) ---
        if "plan" in request.data:
            incoming = request.data.get("plan")
            stored_pk = str(instance.plan_id) if instance.plan_id else None
            stored_slug = instance.plan.slug if instance.plan_id else None
            if str(incoming) not in {stored_pk, stored_slug}:
                raise serializers.ValidationError(
                    {"plan": "Plan cannot be changed after creation."}
                )

        # --- A6: payment proof is write-once BY VALUE (first submit OK) ---
        for field in self.PROOF_FIELDS:
            if field not in request.data:
                continue
            if field == "payment_screenshot":
                # FileField: we cannot compare bytes, so the rule is
                # "one screenshot per subscription" — block only once
                # a file already exists (replacement), allow first upload.
                if getattr(instance, "payment_screenshot", None):
                    raise serializers.ValidationError(
                        {field: f"{field} cannot be changed after initial submission."}
                    )
                continue
            incoming = request.data.get(field)
            stored = getattr(instance, field, None)
            if stored and str(incoming) != str(stored):
                raise serializers.ValidationError(
                    {field: f"{field} cannot be changed after initial submission."}
                )

        # telegram_handle is deliberately NOT blocked here —
        # typo corrections are reasonable at any point before approval.

        return super().update(request, *args, **kwargs)


class TelegramChannelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Telegram channels
    """

    queryset = TelegramChannel.objects.filter(is_active=True)
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAuthenticated]


class TradingSignalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for trading signals.

    A12: scoped to the caller's active, unexpired subscription plans —
    a user with no (or a different-plan) subscription sees no signals.
    """

    queryset = TradingSignal.objects.filter(is_active=True)
    serializer_class = TradingSignalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TradingSignal.objects.filter(
            is_active=True, plan_id__in=_active_plan_ids(self.request.user)
        )


class SignalResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for signal results.

    A12: scoped through ``signal.plan`` to the caller's active,
    unexpired subscription plans (same rule as trading signals).
    """

    queryset = SignalResult.objects.all()
    serializer_class = SignalResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SignalResult.objects.filter(signal__plan_id__in=_active_plan_ids(self.request.user))


# Additional Views
class PublicPlanListView(generics.ListAPIView):
    """
    List public subscription plans
    """

    queryset = TelegramSignalPlan.objects.filter(is_active=True)
    serializer_class = TelegramSignalPlanSerializer
    permission_classes = [AllowAny]


class MySubscriptionView(APIView):
    """
    GET /api/subscriptions/my-subscription/
    Get current user subscription.

    A8: always 200 — active row first, otherwise the latest own row of any
    status (pending_payment/pending_approval are now visible), otherwise
    ``{"subscription": null}`` so the frontend no longer has to treat a 404
    as "no subscription yet".
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = (
            TelegramSubscription.objects.filter(user=request.user, status="active")
            .order_by("-created_at")
            .first()
            or TelegramSubscription.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        if subscription:
            return Response(TelegramSubscriptionSerializer(subscription).data)
        return Response({"subscription": None})


class AdminChannelListView(generics.ListAPIView):
    """
    List all channels for admin
    """

    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAdminUser]


class AdminCreateChannelView(generics.CreateAPIView):
    """
    Create a new channel (admin only)
    """

    queryset = TelegramChannel.objects.all()
    serializer_class = TelegramChannelSerializer
    permission_classes = [IsAdminUser]


# ============================================================================
# NEW TELEGRAM SIGNAL ENDPOINTS (separate from main subscriptions)
# ============================================================================


class TelegramPlanFeaturesSerializer(serializers.Serializer):
    """Serializer for plan features"""

    max_daily_signals = serializers.IntegerField(default=50)
    exchanges_covered = serializers.ListField(child=serializers.CharField())
    risk_level = serializers.CharField()
    include_premium_signals = serializers.BooleanField(default=False)


class TelegramSignalPlanDetailSerializer(serializers.ModelSerializer):
    """Enhanced serializer for Telegram signal plans"""

    # A10: was ``source="feature_dict"`` (a property that exists only on
    # payments.SubscriptionPlan) → DRF silently SkipField'd the key; the
    # intended computation below was dead.  SerializerMethodField wires it.
    features = serializers.SerializerMethodField()

    class Meta:
        model = TelegramSignalPlan
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price_monthly",
            "price_quarterly",
            "price_yearly",
            "features",
            "signals_per_day",
            "exchanges_covered",
            "risk_level",
            "success_rate",
            "max_subscribers",
            "is_active",
            "trial_days",
        ]

    def get_features(self, obj):
        return {
            "max_daily_signals": obj.signals_per_day,
            "exchanges_covered": obj.exchanges_covered or [],
            "risk_level": obj.risk_level,
            "include_premium_signals": "premium" in obj.name.lower(),
        }


class TelegramPlanListView(APIView):
    """
    GET /api/subscriptions/telegram/plans/
    Public endpoint for Telegram signal plans (flat {"plans": [...]} shape)
    """

    permission_classes = [AllowAny]

    def get(self, request):
        cache_key = "telegram_plans_v1"
        data = cache.get(cache_key)

        if not data:
            plans = TelegramSignalPlan.objects.filter(is_active=True).order_by("price_monthly")
            serializer = TelegramSignalPlanDetailSerializer(plans, many=True)
            data = {"plans": serializer.data}
            cache.set(cache_key, data, 3600)

        return Response(data)


class MyTelegramUsageView(APIView):
    """
    GET /api/subscriptions/telegram/my-usage/
    Get user's Telegram subscription usage
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        usage = {"plan": None, "limits": {}, "usage": {}, "is_active": False, "expires_at": None}

        active_sub = (
            TelegramSubscription.objects.filter(
                user=user, status="active", end_date__gte=timezone.now()
            )
            .select_related("plan")
            .first()
        )

        if active_sub:
            plan = active_sub.plan
            usage["plan"] = plan.name
            usage["limits"] = {
                "max_daily_signals": plan.signals_per_day,
                "exchanges": plan.exchanges_covered or [],
            }
            usage["usage"] = {
                "signals_received": active_sub.signals_received,
                "last_signal_date": active_sub.last_signal_date,
            }
            usage["is_active"] = True
            usage["expires_at"] = active_sub.end_date

        return Response(usage)


class TelegramSubscribeView(APIView):
    """
    POST /api/subscriptions/telegram/subscribe/
    Subscribe to Telegram signal plan with payment proof
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # --- required fields (A14: raise → uniform error envelope) ---
        plan_id = request.data.get("plan_id")
        telegram_handle = str(request.data.get("telegram_handle") or "").strip()

        if not plan_id or not telegram_handle:
            raise serializers.ValidationError("plan_id and telegram_handle required")

        # --- A5: accept UUID/int pk OR slug (same param as bot-subscribe) ---
        plan = _resolve_plan(TelegramSignalPlan, plan_id)
        if plan is None:
            raise serializers.ValidationError("Invalid plan_id")

        # Payment validation (A14: uniform envelope instead of flat {"error"})
        payment_screenshot = request.FILES.get("payment_screenshot")
        payment_tx_hash = request.data.get("payment_transaction_hash", "")
        payment_blockchain = request.data.get("payment_blockchain", "")

        if not (payment_screenshot or payment_tx_hash):
            raise serializers.ValidationError("Payment proof required")

        # --- A7: honour the billing cycle instead of hardcoding monthly ---
        billing_cycle = str(request.data.get("billing_cycle") or "monthly")
        cycle_prices = {
            "monthly": plan.price_monthly,
            "quarterly": plan.price_quarterly,
            "yearly": plan.price_yearly,
        }
        if billing_cycle not in cycle_prices:
            raise serializers.ValidationError(
                "billing_cycle must be one of: monthly, quarterly, yearly"
            )

        # --- A7: duplicate check (mirrors bot-subscribe: 409 + metadata) ---
        duplicate = (
            TelegramSubscription.objects.filter(user=request.user, plan=plan)
            .exclude(status__in=["expired", "cancelled", "rejected"])
            .first()
        )
        if duplicate:
            raise Conflict(
                {
                    "message": ("You already have an active or pending subscription to this plan"),
                    "subscription_id": str(duplicate.id),
                    "status": duplicate.status,
                }
            )

        # --- A7: plan capacity — max_subscribers counts non-terminal rows ---
        if plan.max_subscribers is not None:
            taken = (
                TelegramSubscription.objects.filter(plan=plan)
                .exclude(status__in=["expired", "cancelled", "rejected"])
                .count()
            )
            if taken >= plan.max_subscribers:
                raise Conflict("Plan has reached maximum subscribers")

        # Create subscription
        # G5 / FR A7: referee discount frozen at purchase — quoted price is
        # never re-evaluated at approval time.
        # G5 race guard: claim_referee_discount locks the Referral row so two
        # concurrent first-purchases cannot both receive the discount.
        from django.db import transaction as _txn

        from services.referral_rewards import ReferralRewardService, apply_discount

        full_price = cycle_prices[billing_cycle]
        with _txn.atomic():
            pct = ReferralRewardService.claim_referee_discount(request.user)

            subscription = TelegramSubscription.objects.create(
                user=request.user,
                plan=plan,
                status="pending_approval",
                telegram_handle=telegram_handle,
                payment_screenshot=payment_screenshot,
                payment_transaction_hash=payment_tx_hash,
                payment_blockchain=payment_blockchain,
                amount_paid=apply_discount(full_price, pct) if pct > 0 else full_price,
                discount_applied=pct if pct > 0 else None,
                billing_cycle=billing_cycle,
            )

        # A15: the subscribe-time cache.delete("telegram_plans_v1") was
        # removed — subscribing cannot change plan data; invalidation now
        # lives on post_save/post_delete receivers for both plan models.

        return Response(
            {
                "subscription_id": str(subscription.id),
                "status": subscription.status,
                # G5 / FR A7: null = full cycle price (frontend shows plan price)
                "amount_paid": str(subscription.amount_paid),
                "discount_applied": (
                    str(subscription.discount_applied)
                    if subscription.discount_applied is not None
                    else None
                ),
                "message": "Payment received. Admin approval pending.",
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================================
# SUBSCRIPTION PLANS (general, from payments.SubscriptionPlan)
# ============================================================================


class SubscriptionPlanSerializer(serializers.Serializer):
    # G1 (FR A2): full admin-driven plan shape — all values come from the
    # SubscriptionPlan row, never from code constants.
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField()
    price_monthly = serializers.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = serializers.DecimalField(max_digits=10, decimal_places=2)
    annual_discount_pct = serializers.IntegerField()
    sort_order = serializers.IntegerField()
    max_bots_allowed = serializers.IntegerField()
    max_webhooks_allowed = serializers.IntegerField()
    bot_types = serializers.JSONField()
    market = serializers.CharField()
    max_signals_per_month = serializers.IntegerField()
    max_exchanges = serializers.IntegerField()
    features = serializers.JSONField()
    trial_days = serializers.IntegerField()


class PlanListView(APIView):
    """
    GET /api/subscriptions/bot-plans/
    List all active subscription plans (payments.SubscriptionPlan).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        from apps.payments.models import SubscriptionPlan

        # v2: G1 added Model C fields (old v1 shape may be cached)
        cache_key = "subscription_plans_v2"
        data = cache.get(cache_key)
        if not data:
            plans = SubscriptionPlan.objects.filter(is_active=True).order_by(
                "sort_order", "price_monthly"
            )
            serializer = SubscriptionPlanSerializer(plans, many=True)
            data = {"plans": serializer.data}
            cache.set(cache_key, data, 3600)
        return Response(data)


class SubscribeView(APIView):
    """
    POST /api/subscriptions/bot-subscribe/
    Subscribe to a plan. Admin approval required for activation.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.payments.models import BotSubscription, BotSubscriptionPlan, SubscriptionPlan

        # --- required field (A14: uniform envelope) ---
        plan_value = request.data.get("plan_id")
        if not plan_value:
            raise serializers.ValidationError("plan_id required")

        # --- A5: accept slug (historic behaviour) OR numeric pk ---
        plan = _resolve_plan(SubscriptionPlan, plan_value)
        if plan is None:
            raise serializers.ValidationError("Invalid plan_id")

        bot_plan, _ = BotSubscriptionPlan.objects.get_or_create(
            name=plan.name,
            bot_type="custom",
            defaults={
                "price": plan.price_monthly,
                "duration_days": 30,
                "features": {
                    "max_bots": plan.max_bots_allowed,
                    "max_webhooks": plan.max_webhooks_allowed,
                },
                "is_active": True,
                # G5 tier bridge: the referral commission ladder walks
                # subscription.plan.subscription_plan — keep it set on new
                # shims (legacy rows linked by migration 0013 backfill).
                "subscription_plan": plan,
            },
        )
        if not bot_plan.subscription_plan_id:
            # Defensive: a pre-G5 shim whose name missed the 0013 backfill
            # (e.g. plan renamed afterwards).
            bot_plan.subscription_plan = plan
            bot_plan.save(update_fields=["subscription_plan"])

        user = request.user

        existing = (
            BotSubscription.objects.filter(user=user, plan=bot_plan)
            .exclude(status__in=["expired", "cancelled", "rejected"])
            .first()
        )
        if existing:
            # A14: flat {"error": ...} body → uniform envelope; extra keys
            # (subscription_id/status) ride along in error.details.
            raise Conflict(
                {
                    "message": ("You already have an active or pending subscription to this plan"),
                    "subscription_id": str(existing.id),
                    "status": existing.status,
                }
            )

        # G5 / FR A7: referee discount frozen at purchase — the quoted price
        # is never re-evaluated at approval time.
        from services.referral_rewards import ReferralRewardService, apply_discount

        pct = ReferralRewardService.referee_discount_pct(user)

        subscription = BotSubscription.objects.create(
            user=user,
            plan=bot_plan,
            status="pending_payment",
            discount_applied=pct if pct > 0 else None,
            amount_due=apply_discount(bot_plan.price, pct) if pct > 0 else None,
        )

        return Response(
            {
                "subscription_id": str(subscription.id),
                "status": subscription.status,
                # G5 / FR A7: null = full plan price (frontend shows plan price)
                "amount_due": (
                    str(subscription.amount_due) if subscription.amount_due is not None else None
                ),
                "discount_applied": (
                    str(subscription.discount_applied)
                    if subscription.discount_applied is not None
                    else None
                ),
                "message": "Subscription created. Upload payment proof to proceed.",
            },
            status=status.HTTP_201_CREATED,
        )


class MyUsageView(APIView):
    """
    GET /api/subscriptions/bot-my-usage/
    Get current user's subscription plan and usage.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.bots.models import GridBot, MartingaleBot, SignalBot
        from apps.payments.models import BotSubscription

        user = request.user
        active_sub = (
            BotSubscription.objects.filter(
                user=user,
                status="active",
            )
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )

        bots_created = (
            GridBot.objects.filter(user=user, is_deleted=False).count()
            + MartingaleBot.objects.filter(user=user, is_deleted=False).count()
            + SignalBot.objects.filter(user=user, is_deleted=False).count()
        )

        if active_sub:
            plan = active_sub.plan
            features = plan.features if isinstance(plan.features, dict) else {}
            return Response(
                {
                    "plan": {
                        "name": plan.name,
                        "price": str(plan.price),
                        "duration_days": plan.duration_days,
                    },
                    "limits": {
                        "max_bots": features.get("max_bots", 1),
                        "max_webhooks": features.get("max_webhooks", 10),
                    },
                    "usage": {
                        "bots_created": bots_created,
                    },
                    "status": active_sub.status,
                    "expires_at": active_sub.expires_at,
                }
            )

        return Response(
            {
                "plan": None,
                "limits": {"max_bots": 0, "max_webhooks": 0},
                "usage": {"bots_created": bots_created},
                "status": None,
                "expires_at": None,
            }
        )
