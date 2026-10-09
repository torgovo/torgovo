"""
Referrals App Views - Complete Implementation
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.referrals.models import Referral

User = get_user_model()


class ApplyReferralCodeSerializer(serializers.Serializer):
    """Serializer for applying referral code"""

    referral_code = serializers.CharField(max_length=20)

    def validate_referral_code(self, value):
        # Normalize to the format codes are generated/stored in (A2)
        return value.upper().strip()


class MyReferralStatsView(APIView):
    """
    GET /api/referrals/my-stats/
    Returns user's referral statistics
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        referral = Referral.objects.filter(referrer=user).first()
        if not referral:
            referral = Referral.objects.create(
                referrer=user,
                code=user.referral_code,
                bonus_amount=Decimal("0"),
                status="pending",
            )

        # Calculate stats. total_referrals = users who actually signed up with
        # this code (one Referral row per successful referral); rejected/fraud
        # rows are excluded. The old status="paid" filter never matched at
        # runtime (nothing sets "paid"), so the counter was always 0 (A3).
        referrals_made = Referral.objects.filter(referrer=user)
        stats = {
            "referral_code": referral.code,
            "total_referrals": referrals_made.filter(referred_user__isnull=False)
            .exclude(status="rejected")
            .count(),
            "total_bonus_usdt": referrals_made.aggregate(total=Sum("bonus_amount"))["total"]
            or Decimal("0"),
            "referral_link": f"{settings.SITE_URL}/signup?ref={referral.code}",
        }

        return Response(stats)


class ApplyReferralCodeView(APIView):
    """
    POST /api/referrals/apply/
    Apply referral code to authenticated user (post-registration).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # A14: every guard below raises so custom_exception_handler renders
        # the uniform {"error": {code, message, details}, "timestamp"} envelope
        # instead of a one-off flat {"error": "..."} body.
        serializer = ApplyReferralCodeSerializer(data=request.data)
        if not serializer.is_valid():
            raise serializers.ValidationError(serializer.errors)

        referral_code = serializer.validated_data["referral_code"]

        # Find the referrer by their user-level referral code (unique source of
        # truth) — works even if the referrer never opened my-stats/ before (A2)
        referrer = User.objects.filter(referral_code=referral_code).first()
        if not referrer:
            raise serializers.ValidationError("Invalid referral code")

        # Prevent self-referral
        if referrer.id == request.user.id:
            raise serializers.ValidationError("Cannot apply your own referral code")

        # One referral per user ("new user only"): reject users who already
        # have a referrer — via registration or a previous apply/ (A2)
        if (
            request.user.referred_by_id is not None
            or Referral.objects.filter(referred_user=request.user).exists()
        ):
            raise serializers.ValidationError("Referral code already applied")

        # Unlimited applicants: create ONE NEW Referral row per referred user.
        # Never claim/overwrite an existing row — other applicants keep theirs.
        try:
            with transaction.atomic():
                Referral.objects.create(
                    referrer=referrer,
                    code=referrer.referral_code,
                    referred_user=request.user,
                    status="pending",
                    bonus_amount=Decimal("0"),
                )
                # Populate referred_by on the new user
                self._set_referred_by(request.user, referrer)
        except IntegrityError:
            # OneToOne(referred_user) backstop: referred concurrently (A2)
            raise serializers.ValidationError("Referral code already applied")

        return Response(
            {
                "message": "Referral code applied successfully",
                "referrer": referrer.email,
            }
        )

    def _set_referred_by(self, user, referrer):
        user.referred_by = referrer
        user.save(update_fields=["referred_by"])


class ReferralRegistrationMixin:
    """Mixin to handle referral codes during registration.

    Intended to be mixed into UserRegistrationView (or similar).
    Must be listed BEFORE generics.CreateAPIView in the MRO so that
    this mixin's methods are available to the view.
    """

    def apply_referral_after_registration(self, user, code):
        """Apply referral code after successful registration.

        Creates ONE NEW Referral row per referred user — a code can be used by
        unlimited different new signups (A2). Idempotent, guarded against
        self-referral and double-referral.
        Silent on failure — registration must never fail because of a referral.
        """
        if not code:
            return

        # Idempotency: prevent double-application
        if getattr(user, "_referral_applied", False):
            return
        user._referral_applied = True

        if user.referred_by_id is not None:
            return

        # Source of truth for a code is the user-level referral_code (the old
        # Referral.objects.get(code=...) breaks with one row per referral)
        referrer = User.objects.filter(referral_code=code.upper().strip()).first()
        if referrer is None:
            return

        # Guard: self-referral
        if referrer == user:
            return

        try:
            with transaction.atomic():
                # One row per successful referral — never claim/overwrite an
                # existing row (the old "claimed -> skip" dropped signups 2+)
                Referral.objects.create(
                    referrer=referrer,
                    code=referrer.referral_code,
                    referred_user=user,
                    status="pending",
                )

                user.referred_by = referrer
                user.save(update_fields=["referred_by"])
        except IntegrityError:
            # Already referred (race with apply/) — treat as silent no-op
            return

        return {
            "referral_applied": True,
            "referrer": referrer.email,
        }
