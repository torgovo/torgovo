"""
Views for Telegram signals subscription management
"""

from django.core.cache import cache
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
        # server-controlled. Plan stays writable so users can pick a plan.
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

        Once a subscription leaves ``pending_payment`` status, no field
        can be modified — the record is frozen for admin review.  While
        still in ``pending_payment``, the user may correct their telegram
        handle (typo fixes) but may NOT change the plan they chose or
        alter payment proof after initial submission.  These restrictions
        prevent fraud: a user cannot get approved on a cheap plan and
        switch post-approval, or alter submitted proof after admin review.
        """
        instance = self.get_object()

        # --- Status gate: only editable during payment submission phase ---
        if instance.status != "pending_payment":
            raise serializers.ValidationError("This subscription can no longer be edited.")

        # --- Plan is write-once from creation ---
        if "plan" in request.data:
            raise serializers.ValidationError({"plan": "Plan cannot be changed after creation."})

        # --- Payment proof fields are write-once ---
        for field in self.PROOF_FIELDS:
            if field in request.data:
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
    ViewSet for trading signals
    """

    queryset = TradingSignal.objects.filter(is_active=True)
    serializer_class = TradingSignalSerializer
    permission_classes = [IsAuthenticated]


class SignalResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for signal results
    """

    queryset = SignalResult.objects.all()
    serializer_class = SignalResultSerializer
    permission_classes = [IsAuthenticated]


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
    Get current user subscription
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = TelegramSubscription.objects.filter(
            user=request.user, status="active"
        ).first()
        if subscription:
            serializer = TelegramSubscriptionSerializer(subscription)
            return Response(serializer.data)
        return Response({"message": "No active subscription"}, status=status.HTTP_404_NOT_FOUND)


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

    features = TelegramPlanFeaturesSerializer(source="feature_dict", read_only=True)

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
    GET /api/telegram/plans/
    Public endpoint for Telegram signal plans
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
    GET /api/telegram/my-usage/
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
    POST /api/telegram/subscribe/
    Subscribe to Telegram signal plan with payment proof
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get("plan_id")
        telegram_handle = request.data.get("telegram_handle", "").strip()

        if not plan_id or not telegram_handle:
            return Response(
                {"error": "plan_id and telegram_handle required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan = TelegramSignalPlan.objects.get(id=plan_id, is_active=True)
        except TelegramSignalPlan.DoesNotExist:
            return Response({"error": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

        # Payment validation
        payment_screenshot = request.FILES.get("payment_screenshot")
        payment_tx_hash = request.data.get("payment_transaction_hash", "")
        payment_blockchain = request.data.get("payment_blockchain", "")

        if not (payment_screenshot or payment_tx_hash):
            return Response({"error": "Payment proof required"}, status=status.HTTP_400_BAD_REQUEST)

        # Create subscription
        subscription = TelegramSubscription.objects.create(
            user=request.user,
            plan=plan,
            status="pending_approval",
            telegram_handle=telegram_handle,
            payment_screenshot=payment_screenshot,
            payment_transaction_hash=payment_tx_hash,
            payment_blockchain=payment_blockchain,
            amount_paid=plan.price_monthly,
            billing_cycle="monthly",
        )

        cache.delete("telegram_plans_v1")

        return Response(
            {
                "subscription_id": str(subscription.id),
                "status": subscription.status,
                "message": "Payment received. Admin approval pending.",
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================================
# SUBSCRIPTION PLANS (general, from payments.SubscriptionPlan)
# ============================================================================


class SubscriptionPlanSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    price_monthly = serializers.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_bots_allowed = serializers.IntegerField()
    max_webhooks_allowed = serializers.IntegerField()
    features = serializers.JSONField()
    trial_days = serializers.IntegerField()


class PlanListView(APIView):
    """
    GET /api/subscriptions/plans/
    List all active subscription plans.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        from apps.payments.models import SubscriptionPlan

        cache_key = "subscription_plans_v1"
        data = cache.get(cache_key)
        if not data:
            plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price_monthly")
            serializer = SubscriptionPlanSerializer(plans, many=True)
            data = {"plans": serializer.data}
            cache.set(cache_key, data, 3600)
        return Response(data)


class SubscribeView(APIView):
    """
    POST /api/subscriptions/subscribe/
    Subscribe to a plan. Admin approval required for activation.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.payments.models import BotSubscription, BotSubscriptionPlan, SubscriptionPlan

        plan_slug = request.data.get("plan_id")
        if not plan_slug:
            return Response({"error": "plan_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = SubscriptionPlan.objects.get(slug=plan_slug, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

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
            },
        )

        user = request.user

        existing = (
            BotSubscription.objects.filter(user=user, plan=bot_plan)
            .exclude(status__in=["expired", "cancelled", "rejected"])
            .first()
        )
        if existing:
            return Response(
                {
                    "error": "You already have an active or pending subscription to this plan",
                    "subscription_id": str(existing.id),
                    "status": existing.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        subscription = BotSubscription.objects.create(
            user=user,
            plan=bot_plan,
            status="pending_payment",
        )

        return Response(
            {
                "subscription_id": str(subscription.id),
                "status": subscription.status,
                "message": "Subscription created. Upload payment proof to proceed.",
            },
            status=status.HTTP_201_CREATED,
        )


class MyUsageView(APIView):
    """
    GET /api/subscriptions/my-usage/
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
