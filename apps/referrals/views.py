"""
Referrals App Views - Complete Implementation
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.referrals.models import Referral

User = get_user_model()


class ReferralStatsSerializer(serializers.Serializer):
    """Serializer for referral stats response"""

    referral_code = serializers.CharField(max_length=20)
    total_referrals = serializers.IntegerField(read_only=True)
    total_bonus_usdt = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    referral_link = serializers.SerializerMethodField()

    def get_referral_link(self, obj):
        return f"{settings.SITE_URL}/signup?ref={obj['referral_code']}"


class ApplyReferralCodeSerializer(serializers.Serializer):
    """Serializer for applying referral code"""

    referral_code = serializers.CharField(max_length=20)


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

        # Calculate stats
        referrals_made = Referral.objects.filter(referrer=user)
        stats = {
            "referral_code": referral.code,
            "total_referrals": referrals_made.filter(status="paid").count(),
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
        serializer = ApplyReferralCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        referral_code = serializer.validated_data["referral_code"]

        # Find the referrer by code
        referrer_referral = Referral.objects.filter(code=referral_code).first()
        if not referrer_referral:
            return Response({"error": "Invalid referral code"}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent self-referral
        if referrer_referral.referrer_id == request.user.id:
            return Response(
                {"error": "Cannot apply your own referral code"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user already has a referrer
        existing_referral = Referral.objects.filter(referred_user=request.user).first()
        if existing_referral:
            return Response(
                {"error": "Referral code already applied"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Update the referral record to mark this user as referred
        referrer_referral.referred_user = request.user
        referrer_referral.status = "pending"
        referrer_referral.save()

        # Populate referred_by on the new user
        self._set_referred_by(request.user, referrer_referral.referrer)

        return Response(
            {
                "message": "Referral code applied successfully",
                "referrer": referrer_referral.referrer.email,
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

        Idempotent, guarded against self-referral and duplicate referrers.
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

        try:
            referral = Referral.objects.select_related("referrer").get(code=code)
        except Referral.DoesNotExist:
            return

        referrer = referral.referrer

        # Guard: self-referral
        if referrer == user:
            return

        # Guard: referred_user already claimed
        if referral.referred_user_id is not None:
            return

        with transaction.atomic():
            # Lock the row for atomic claim
            referral = Referral.objects.select_for_update().get(pk=referral.pk)

            # Re-check under lock
            if referral.referred_user_id is not None:
                return

            referral.referred_user = user
            referral.save(update_fields=["referred_user"])

            user.referred_by = referrer
            user.save(update_fields=["referred_by"])

        return {
            "referral_applied": True,
            "referrer": referrer.email,
        }
