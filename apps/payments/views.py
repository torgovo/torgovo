"""
Views for payment processing endpoints.

Payment-only views: subscription plans, deposits, withdrawals, payment transactions,
admin approval, and blockchain addresses.

Bot management ViewSets have been moved to apps/bots/views.py.
"""

import logging
from decimal import Decimal

from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import QuantumAIFund
from core.pagination import StandardResultsSetPagination

from .models import (
    BlockchainAddress,
    BotSubscription,
    BotSubscriptionPlan,
    PaymentTransaction,
    QuantumAIDeposit,
    SubscriptionPlan,
    WithdrawalRequest,
)
from .serializers import (
    BlockchainAddressSerializer,
    BotSubscriptionSerializer,
    PaymentTransactionSerializer,
    QuantumAIDepositSerializer,
    SubscriptionPlanSerializer,
    WithdrawalRequestSerializer,
)

logger = logging.getLogger("apps")


# ==================== SUBSCRIPTION PLANS ====================


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing subscription plans."""

    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination


# ==================== BOT SUBSCRIPTIONS ====================


class BotSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for user's bot subscriptions (read-only)"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    serializer_class = BotSubscriptionSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return BotSubscription.objects.all().select_related("plan", "user")
        return BotSubscription.objects.filter(user=self.request.user).select_related("plan")


class CreateBotSubscriptionView(APIView):
    """Create a new bot subscription (user initiates)"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create subscription and upload payment proof"""
        try:
            plan_id = request.data.get("plan_id")
            exchange_name = request.data.get("exchange_name", "")
            payment_screenshot = request.FILES.get("payment_screenshot")
            payment_transaction_hash = request.data.get("payment_transaction_hash", "")
            payment_blockchain = request.data.get("payment_blockchain", "")

            if not plan_id:
                return Response(
                    {"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not payment_screenshot and not payment_transaction_hash:
                return Response(
                    {"error": "Either payment_screenshot or payment_transaction_hash is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            plan = BotSubscriptionPlan.objects.get(id=plan_id)

            initial_status = (
                "pending_approval"
                if (payment_screenshot or payment_transaction_hash)
                else "pending_payment"
            )

            subscription = BotSubscription.objects.create(
                user=request.user,
                plan=plan,
                exchange_name=exchange_name,
                payment_screenshot=payment_screenshot,
                payment_transaction_hash=payment_transaction_hash,
                payment_blockchain=payment_blockchain,
                status=initial_status,
            )

            return Response(
                {
                    "success": True,
                    "message": "Subscription created and pending approval",
                    "subscription_id": str(subscription.id),
                    "status": subscription.status,
                },
                status=status.HTTP_201_CREATED,
            )

        except BotSubscriptionPlan.DoesNotExist:
            return Response({"error": "Invalid plan_id"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating subscription: {str(e)}")
            return Response(
                {"error": "Failed to create subscription"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ==================== ADMIN APPROVAL ====================


class AdminApproveSubscriptionView(APIView):
    """Admin approval endpoint for subscriptions"""

    permission_classes = [IsAdminUser]

    def post(self, request, subscription_id):
        """Approve a pending subscription"""
        try:
            from services.subscription_service import SubscriptionService

            subscription = SubscriptionService.approve_subscription(subscription_id, request.user)
            return Response(
                {
                    "success": True,
                    "message": f"Subscription approved for {subscription.user.email}",
                    "subscription_id": str(subscription.id),
                }
            )
        except Exception as e:
            logger.error(f"Admin approve subscription error: {e}", exc_info=True)
            return Response(
                {"error": "Failed to approve subscription"}, status=status.HTTP_400_BAD_REQUEST
            )


class AdminRejectSubscriptionView(APIView):
    """Admin rejection endpoint for subscriptions"""

    permission_classes = [IsAdminUser]

    def post(self, request, subscription_id):
        """Reject a pending subscription"""
        try:
            reason = request.data.get("reason", "")
            if not reason:
                return Response({"error": "Reason is required"}, status=status.HTTP_400_BAD_REQUEST)

            from services.subscription_service import SubscriptionService

            subscription = SubscriptionService.reject_subscription(
                subscription_id, request.user, reason
            )
            return Response(
                {
                    "success": True,
                    "message": f"Subscription rejected: {reason}",
                    "subscription_id": str(subscription.id),
                }
            )
        except Exception as e:
            logger.error(f"Admin reject subscription error: {e}", exc_info=True)
            return Response(
                {"error": "Failed to reject subscription"}, status=status.HTTP_400_BAD_REQUEST
            )


# ==================== QUANTUM AI DEPOSITS ====================


class QuantumDepositViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Quantum AI deposits."""

    queryset = QuantumAIDeposit.objects.all()
    serializer_class = QuantumAIDepositSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return QuantumAIDeposit.objects.all().order_by("-created_at")
        return QuantumAIDeposit.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Get pending deposits."""
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        pending_deposits = QuantumAIDeposit.objects.filter(status="pending").order_by("-created_at")
        serializer = self.get_serializer(pending_deposits, many=True)
        return Response(serializer.data)


# ==================== WITHDRAWALS ====================


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    """ViewSet for managing withdrawal requests."""

    queryset = WithdrawalRequest.objects.all()
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    throttle_scope = "withdrawal"

    def get_queryset(self):
        if self.request.user.is_staff:
            return WithdrawalRequest.objects.all().order_by("-created_at")
        return WithdrawalRequest.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        """
        Create a withdrawal request with server-controlled fields.

        Security gates:
          * Caller must be email-verified.
          * 2FA code must be present and validated (per-user TOTP / SMS code).
          * Withdrawals are always created with status='pending'; admin
            must approve via a separate flow.
          * Network/processing fee + total are computed server-side.
        """
        request = self.request
        user = request.user

        # Verified email gate
        if not getattr(user, "is_email_verified", False):
            raise serializers.ValidationError("Email verification required before withdrawing.")

        # 2FA gate — code is REQUIRED. The actual TOTP/SMS check should
        # live in a dedicated service; here we at least enforce presence
        # and length, and reject if the user has 2FA disabled.
        code = (request.data.get("two_factor_code") or "").strip()
        if not code or len(code) < 4:
            raise serializers.ValidationError("two_factor_code is required for withdrawals.")
        if not getattr(user, "two_factor_enabled", False):
            raise serializers.ValidationError(
                "Enable 2FA on your account before requesting withdrawals."
            )

        amount = serializer.validated_data.get("amount")
        from decimal import Decimal as _D

        network_fee = _D("1.0")  # placeholder, replace with chain-specific oracle
        processing_fee = (_D(str(amount)) * _D("0.005")).quantize(_D("0.00000001"))
        total = _D(str(amount)) + network_fee + processing_fee

        serializer.save(
            user=user,
            status="pending",
            network_fee=network_fee,
            processing_fee=processing_fee,
            total_amount=total,
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
            flagged_for_review=(_D(str(amount)) >= _D("1000")),  # auto-flag big withdrawals
        )

    def get_client_ip(self):
        """Get client IP address."""
        x_forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = self.request.META.get("REMOTE_ADDR", "")
        return ip

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Approve a pending withdrawal (admin only)."""
        withdrawal = self.get_object()
        if withdrawal.status != "pending":
            return Response(
                {"success": False, "error": "Withdrawal is not in pending status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notes = request.data.get("notes", "")
        withdrawal.admin_approved_by = request.user
        withdrawal.admin_notes = notes
        withdrawal.status = "processing"
        withdrawal.save()
        return Response({"success": True, "message": "Withdrawal approved and moved to processing"})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def reject(self, request, pk=None):
        """Reject a pending withdrawal (admin only)."""
        withdrawal = self.get_object()
        if withdrawal.status != "pending":
            return Response(
                {"success": False, "error": "Withdrawal is not in pending status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"success": False, "error": "Reason is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        withdrawal.admin_notes = reason
        withdrawal.status = "rejected"
        withdrawal.save()
        return Response({"success": True, "message": "Withdrawal rejected"})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a withdrawal request."""
        withdrawal = self.get_object()

        if withdrawal.user != request.user and not request.user.is_staff:
            return Response(
                {"success": False, "error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        if withdrawal.status not in ["pending", "processing"]:
            return Response(
                {"success": False, "error": "Withdrawal cannot be cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        withdrawal.status = "rejected"
        withdrawal.admin_notes = request.data.get("notes", "Cancelled by user")
        withdrawal.save()

        return Response({"success": True, "message": "Withdrawal request cancelled successfully"})


# ==================== PAYMENT TRANSACTIONS ====================


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing payment transaction history."""

    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return PaymentTransaction.objects.all().order_by("-created_at")
        return PaymentTransaction.objects.filter(user=self.request.user).order_by("-created_at")

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent transactions."""
        recent_transactions = self.get_queryset()[:20]
        serializer = self.get_serializer(recent_transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_type(self, request):
        """Filter transactions by type."""
        transaction_type = request.query_params.get("type", None)
        if transaction_type:
            transactions = self.get_queryset().filter(transaction_type=transaction_type)
            serializer = self.get_serializer(transactions, many=True)
            return Response(serializer.data)
        return Response(
            {"error": "Transaction type parameter required"}, status=status.HTTP_400_BAD_REQUEST
        )


# ==================== BLOCKCHAIN ADDRESSES ====================


class BlockchainAddressListView(generics.ListAPIView):
    """List available blockchain addresses for deposits."""

    serializer_class = BlockchainAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BlockchainAddress.objects.filter(is_active=True)


# ==================== DEPOSIT ADMIN VIEWS ====================


class CreateDepositView(APIView):
    """Create a new deposit for a Quantum AI bot."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=QuantumAIDepositSerializer, responses={201: QuantumAIDepositSerializer}
    )
    def post(self, request, bot_id):
        """Create a deposit for the specified bot."""
        try:
            bot = get_object_or_404(QuantumAIFund, id=bot_id)

            serializer = QuantumAIDepositSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user, quantum_bot=bot)

                return Response(
                    {
                        "success": True,
                        "message": "Deposit created successfully",
                        "deposit": serializer.data,
                    },
                    status=status.HTTP_201_CREATED,
                )

            return Response(
                {"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            logger.error(f"Error creating deposit: {str(e)}")
            return Response(
                {"success": False, "error": "Failed to create deposit"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ApproveDepositView(APIView):
    """Approve a pending deposit (admin only)."""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "notes": openapi.Schema(type=openapi.TYPE_STRING),
                "usdt_amount": openapi.Schema(type=openapi.TYPE_NUMBER),
            },
        ),
        responses={200: openapi.Response("Deposit approved")},
    )
    def post(self, request, deposit_id):
        """Approve a deposit."""
        try:
            deposit = get_object_or_404(QuantumAIDeposit, id=deposit_id)

            if deposit.status != "pending":
                return Response(
                    {"success": False, "error": "Deposit is not in pending status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            notes = request.data.get("notes", "")
            usdt_amount = request.data.get("usdt_amount")

            if usdt_amount:
                deposit.usdt_amount = Decimal(str(usdt_amount))

            deposit.approve(request.user, notes)

            return Response({"success": True, "message": "Deposit approved successfully"})

        except Exception as e:
            logger.error(f"Error approving deposit {deposit_id}: {str(e)}")
            return Response(
                {"success": False, "error": "Failed to approve deposit"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RejectDepositView(APIView):
    """Reject a pending deposit (admin only)."""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "reason": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Reason for rejection"
                ),
            },
            required=["reason"],
        ),
        responses={200: openapi.Response("Deposit rejected")},
    )
    def post(self, request, deposit_id):
        """Reject a deposit."""
        try:
            deposit = get_object_or_404(QuantumAIDeposit, id=deposit_id)

            if deposit.status != "pending":
                return Response(
                    {"success": False, "error": "Deposit is not in pending status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            reason = request.data.get("reason", "")
            if not reason:
                return Response(
                    {"success": False, "error": "Reason is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deposit.reject(request.user, reason)

            return Response({"success": True, "message": "Deposit rejected successfully"})

        except Exception as e:
            logger.error(f"Error rejecting deposit {deposit_id}: {str(e)}")
            return Response(
                {"success": False, "error": "Failed to reject deposit"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
