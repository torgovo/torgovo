"""
Views for payment processing endpoints.

Payment-only views: subscription plans, deposits, withdrawals, payment transactions,
admin approval, and blockchain addresses.

Bot management ViewSets have been moved to apps/bots/views.py.
"""

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import QuantumAIFund
from core.exceptions import ServiceUnavailable
from core.pagination import StandardResultsSetPagination

from .models import (
    BlockchainAddress,
    BotSubscription,
    BotSubscriptionPlan,
    InvestorDeposit,
    PaymentCode,
    PaymentCoin,
    PaymentTransaction,
    ReferralPayoutRequest,
    SubscriptionPlan,
    WithdrawalRequest,
)
from .serializers import (
    BlockchainAddressSerializer,
    BotSubscriptionSerializer,
    InvestorDepositSerializer,
    PaymentCodeCreateSerializer,
    PaymentCodeProofSerializer,
    PaymentCodeSerializer,
    PaymentCoinSerializer,
    PaymentTransactionSerializer,
    ReferralPayoutRequestSerializer,
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

            # G5 / FR A7: referee discount frozen at purchase — recomputed on
            # every submit, so a re-subscribe (returning payer) correctly
            # clears any stale first-payment discount instead of keeping it.
            # G5 race guard: claim_referee_discount locks the Referral row so
            # two concurrent first-purchases cannot both receive the discount.
            from django.db import transaction as _txn

            from services.referral_rewards import ReferralRewardService, apply_discount

            with _txn.atomic():
                pct = ReferralRewardService.claim_referee_discount(request.user)
                discount_pct = pct if pct > 0 else None
                net_price = apply_discount(plan.price, pct) if pct > 0 else None

                initial_status = (
                    "pending_approval"
                    if (payment_screenshot or payment_transaction_hash)
                    else "pending_payment"
                )

                # G4 / FR A6 re-subscribe: unique_together ["user","plan"] means
                # a returning user already has a row (possibly "expired"). Reuse
                # it — reset payment fields + status, KEEP started_at/expires_at
                # and all bot FKs (retained data). Only after admin re-approval
                # does approve() stamp a fresh clock.
                subscription = BotSubscription.objects.filter(user=request.user, plan=plan).first()
                if subscription:
                    subscription.exchange_name = exchange_name
                    if payment_screenshot:
                        subscription.payment_screenshot = payment_screenshot
                    if payment_transaction_hash:
                        subscription.payment_transaction_hash = payment_transaction_hash
                    if payment_blockchain:
                        subscription.payment_blockchain = payment_blockchain
                    subscription.status = initial_status
                    subscription.rejection_reason = ""  # clear old rejection on re-submit
                    subscription.discount_applied = discount_pct
                    subscription.amount_due = net_price
                    subscription.save()
                else:
                    subscription = BotSubscription.objects.create(
                        user=request.user,
                        plan=plan,
                        exchange_name=exchange_name,
                        payment_screenshot=payment_screenshot,
                        payment_transaction_hash=payment_transaction_hash,
                        payment_blockchain=payment_blockchain,
                        status=initial_status,
                        discount_applied=discount_pct,
                        amount_due=net_price,
                    )

            return Response(
                {
                    "success": True,
                    "message": "Subscription created and pending approval",
                    "subscription_id": str(subscription.id),
                    "status": subscription.status,
                    # G5 / FR A7: null = full plan price (frontend shows plan price)
                    "amount_due": (
                        str(subscription.amount_due)
                        if subscription.amount_due is not None
                        else None
                    ),
                    "discount_applied": (
                        str(subscription.discount_applied)
                        if subscription.discount_applied is not None
                        else None
                    ),
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

    queryset = InvestorDeposit.objects.all()
    serializer_class = InvestorDepositSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return InvestorDeposit.objects.all().order_by("-created_at")
        return InvestorDeposit.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Get pending deposits."""
        if not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        pending_deposits = InvestorDeposit.objects.filter(status="pending").order_by("-created_at")
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

        # 2FA gate — code is REQUIRED and must actually verify against the
        # user's stored TOTP secret (S-3 fix: was presence/length-only).
        code = (request.data.get("two_factor_code") or "").strip()
        if not code or len(code) < 4:
            raise serializers.ValidationError("two_factor_code is required for withdrawals.")
        if not getattr(user, "two_factor_enabled", False):
            raise serializers.ValidationError(
                "Enable 2FA on your account before requesting withdrawals."
            )

        from services.two_factor import decrypt_totp_secret, verify_totp_code

        secret = decrypt_totp_secret(getattr(user, "totp_secret", ""))
        if secret is None or not verify_totp_code(secret, code, window=1):
            raise serializers.ValidationError("Invalid or expired two_factor_code.")

        # SEC-2: two_factor_code is a serializer-only field (not on the model).
        # Pop it from validated_data so ModelSerializer.create() doesn't pass
        # it to WithdrawalRequest.objects.create().
        serializer.validated_data.pop("two_factor_code", None)

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
        request_body=InvestorDepositSerializer, responses={201: InvestorDepositSerializer}
    )
    def post(self, request, bot_id):
        """Create a deposit for the specified bot."""
        try:
            bot = get_object_or_404(QuantumAIFund, id=bot_id)

            serializer = InvestorDepositSerializer(data=request.data)
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
        """Approve a deposit and open the A5 Quantum AI lock (§A5/G3)."""
        from django.db import transaction as db_transaction

        from apps.bots.models import QuantumAIFund
        from services.quantum_locks import QuantumLockError, QuantumLockService

        try:
            deposit = get_object_or_404(InvestorDeposit, id=deposit_id)

            if deposit.status != "pending":
                return Response(
                    {"success": False, "error": "Deposit is not in pending status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            notes = request.data.get("notes", "")
            usdt_amount = request.data.get("usdt_amount")

            if usdt_amount:
                try:
                    deposit.usdt_amount = Decimal(str(usdt_amount))
                except Exception:
                    return Response(
                        {"success": False, "error": "Invalid usdt_amount"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # A5 capital: admin-entered USDT value wins; a USDT-denominated
            # deposit falls back to its raw amount (single balance-of-record).
            capital = deposit.usdt_amount
            if capital is None and (deposit.currency or "").upper() == "USDT":
                capital = deposit.amount

            fund = deposit.fund or QuantumAIFund.objects.filter(is_active=True).first()
            if fund is None or not fund.is_active:
                # Same hard requirement as subscription approval — a deposit
                # must never land without an A5 lock ledger.
                return Response(
                    {
                        "success": False,
                        "error": "No active Quantum AI fund — create one before approving.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if capital is None:
                return Response(
                    {
                        "success": False,
                        "error": "usdt_amount is required — enter the deposit value in USDT.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                lock_days = int(request.data.get("lock_days") or fund.default_lock_days)
            except (TypeError, ValueError):
                return Response(
                    {"success": False, "error": "Invalid lock_days"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Approve + lock creation commit together — either both or neither.
            with db_transaction.atomic():
                deposit.approve(request.user, notes)
                lock = QuantumLockService.create_lock(
                    user=deposit.user,
                    fund=fund,
                    amount=capital,
                    lock_days=lock_days,
                    deposit=deposit,
                )

            return Response(
                {
                    "success": True,
                    "message": "Deposit approved successfully",
                    "lock_id": str(lock.id),
                    "matures_at": lock.matures_at.isoformat(),
                }
            )

        except QuantumLockError as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
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
            deposit = get_object_or_404(InvestorDeposit, id=deposit_id)

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


# ==================== G2 / FR A3 — MANUAL MULTI-COIN PAYMENTS ====================


class PaymentCoinListView(APIView):
    """Public read of the admin-configured coin/chain list (step-0 picker)."""

    permission_classes = [AllowAny]

    def get(self, request):
        coins = PaymentCoin.objects.filter(is_active=True, deposit_address__gt="")
        return Response(PaymentCoinSerializer(coins, many=True).data)


class PaymentCodeCreateView(APIView):
    """
    POST /api/v1/payments/payment-codes/ — step 1: user picks a plan.

    Resolves plan (pk or slug), freezes fiat amount, runs duplicate/capacity
    pre-flight (409), requires at least one configured coin (400), returns
    the unique code. Quote/price-lock happens on the detail GET.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PaymentCodeCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        if not PaymentCoin.objects.filter(is_active=True, deposit_address__gt="").exists():
            raise serializers.ValidationError({"coin": "No payment coin is configured yet"})

        # G5 / FR A7: referee discount baked into fiat_amount at code
        # creation — the quote, verify and fulfill paths all read fiat_amount,
        # so they price the discounted amount end-to-end with no extra hooks.
        from services.referral_rewards import ReferralRewardService, apply_discount

        from .services.fulfill import check_order_allowed, plan_fiat_amount

        fiat = plan_fiat_amount(
            data["order_kind"],
            data.get("telegram_plan") or data.get("bot_plan"),
            data.get("billing_cycle", "monthly"),
        )
        pct = ReferralRewardService.referee_discount_pct(request.user)
        if pct > 0:
            fiat = apply_discount(fiat, pct)

        code = PaymentCode(
            user=request.user,
            order_kind=data["order_kind"],
            telegram_plan=data.get("telegram_plan"),
            bot_plan=data.get("bot_plan"),
            billing_cycle=data.get("billing_cycle", "monthly"),
            fiat_amount=fiat,
            discount_applied=pct if pct > 0 else None,
        )
        # Duplicate/capacity pre-flight BEFORE allocating the code (fail early).
        check_order_allowed(code)
        code.save()
        return Response(PaymentCodeSerializer(code).data, status=status.HTTP_201_CREATED)


def _resolve_requested_coin(coin_id: str | None) -> PaymentCoin | None:
    """
    Resolve a client-requested payment coin (shared by GET detail + re-request).

    Only active, address-configured coins are selectable. No coin_id → first
    configured coin by sort_order (same default the picker starts on).
    """
    configured = PaymentCoin.objects.filter(is_active=True, deposit_address__gt="")
    if coin_id:
        # Guard: a malformed UUID would raise out of the ORM as a 500.
        try:
            coin = configured.filter(pk=coin_id).first()
        except (ValueError, ValidationError):
            coin = None
        if coin is None:
            raise serializers.ValidationError({"coin_id": "Unknown or unconfigured coin"})
        return coin
    return configured.first()


class PaymentCodeDetailView(APIView):
    """
    GET /api/v1/payments/payment-codes/<code>/ — step 2: live quote.

    Re-locks the price when the latest quote is past TTL while the payment
    window is open (or the caller switched coins via ?coin_id=). Once the
    window ends the quote stays expired — the client must re-request via
    POST .../quote/. Once proof is submitted the frozen quote returns
    unchanged (manual verify at launch).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        code_obj = get_object_or_404(PaymentCode, code=code, user=request.user)
        coin = _resolve_requested_coin(request.query_params.get("coin_id"))

        from .services.quote import QuoteUnavailable, get_or_refresh_quote

        if coin is not None:
            try:
                get_or_refresh_quote(code_obj, coin)
            except QuoteUnavailable:
                # Price feed down → say so cleanly (standard envelope); the
                # client retries — never returns a stale/absent amount as
                # if it were current.
                raise ServiceUnavailable("Price feed unavailable — retry shortly")
        return Response(PaymentCodeSerializer(code_obj).data)


class PaymentCodeQuoteView(APIView):
    """
    POST /api/v1/payments/payment-codes/<code>/quote/ — explicit re-request.

    FR A3: after the payment window ends the user must re-request a quote
    at the then-current price (no silent re-lock). Resets the window
    (per-coin admin-configurable, default 6h) and re-locks. Body
    {coin_id?} selects/switches the coin; response = same payload as GET.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        code_obj = get_object_or_404(PaymentCode, code=code, user=request.user)
        if code_obj.status != "awaiting_payment":
            raise serializers.ValidationError({"detail": "Code is not awaiting payment"})

        from .services.quote import QuoteUnavailable, renew_quote

        try:
            coin = _resolve_requested_coin(request.data.get("coin_id"))
        except serializers.ValidationError:
            raise  # unknown/unconfigured coin → 400 with field error
        try:
            renew_quote(code_obj, coin)
        except ValueError:
            # No configured coin exists to price against.
            raise serializers.ValidationError({"coin_id": "Unknown or unconfigured coin"})
        except QuoteUnavailable:
            raise ServiceUnavailable("Price feed unavailable — retry shortly")
        return Response(PaymentCodeSerializer(code_obj).data)


class PaymentCodeProofView(APIView):
    """
    POST /api/v1/payments/payment-codes/<code>/proof/ — step 3: submit proof.

    Refreshes the quote if stale (auto-reprice up to submission), freezes
    rate/amount onto the code, creates the pending_approval subscription,
    marks the code `submitted` (admin verifies manually at launch).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        code_obj = get_object_or_404(PaymentCode, code=code, user=request.user)
        ser = PaymentCodeProofSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from .services.fulfill import fulfill_payment_code
        from .services.quote import QuoteUnavailable, get_or_refresh_quote

        # Final re-price before freezing: a stale quote is re-locked here so
        # the admin verifies against a rate the user actually saw. If the
        # client never loaded the detail GET, lock against the first
        # configured coin so locked_* is always populated.
        try:
            if code_obj.current_quote is None:
                fallback_coin = (
                    PaymentCoin.objects.filter(is_active=True, deposit_address__gt="")
                    .order_by("sort_order")
                    .first()
                )
                if fallback_coin is not None:
                    from .services.quote import create_quote

                    create_quote(code_obj, fallback_coin)
            get_or_refresh_quote(code_obj, None)
        except QuoteUnavailable:
            raise ServiceUnavailable("Price feed unavailable — retry shortly")

        subscription = fulfill_payment_code(
            code_obj,
            payment_screenshot=ser.validated_data.get("payment_screenshot"),
            payment_transaction_hash=ser.validated_data.get("payment_transaction_hash", ""),
            payment_blockchain=ser.validated_data.get("payment_blockchain", ""),
            telegram_handle=ser.validated_data.get("telegram_handle", ""),
        )
        code_obj.refresh_from_db()
        payload = PaymentCodeSerializer(code_obj).data
        payload["subscription_id"] = str(subscription.id)
        return Response(payload, status=status.HTTP_201_CREATED)


# ==================== REFERRAL PAYOUT REQUESTS (G5 / FR A7) ====================


class AdminPayoutRequestListView(APIView):
    """GET /api/v1/payments/admin/payout-requests/ — staff list (default pending)."""

    permission_classes = [IsAdminUser]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="pending | approved | rejected | all (default pending)",
            )
        ],
        responses={200: ReferralPayoutRequestSerializer(many=True)},
    )
    def get(self, request):
        status_filter = request.query_params.get("status", "pending")
        qs = ReferralPayoutRequest.objects.select_related("user", "decided_by").order_by(
            "-requested_at"
        )
        if status_filter != "all":
            qs = qs.filter(status=status_filter)
        return Response(ReferralPayoutRequestSerializer(qs[:200], many=True).data)


class AdminPayoutRequestDecideView(APIView):
    """POST approve|reject a commission payout request (admin only).

    Approve body: {payout_amount, notes} — payout_amount is what was actually
    paid to the referrer including fees; settles pending accruals FIFO and
    books one `referral_payout` ledger transaction. Reject body: {notes}.
    `action` is injected via as_view(action=...), mirroring the deposits
    approve/reject path convention.
    """

    permission_classes = [IsAdminUser]
    action = None  # "approve" | "reject" (set by as_view)

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "payout_amount": openapi.Schema(type=openapi.TYPE_NUMBER),
                "notes": openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: ReferralPayoutRequestSerializer()},
    )
    def post(self, request, request_id):
        from services.referral_rewards import ReferralRewardError, ReferralRewardService

        try:
            if self.action == "approve":
                req = ReferralRewardService.approve_payout_request(
                    request_id=request_id,
                    admin=request.user,
                    payout_amount=request.data.get("payout_amount"),
                    notes=str(request.data.get("notes") or ""),
                )
            else:
                req = ReferralRewardService.reject_payout_request(
                    request_id=request_id,
                    admin=request.user,
                    notes=str(request.data.get("notes") or ""),
                )
        except ReferralPayoutRequest.DoesNotExist:
            return Response(
                {"success": False, "error": "Payout request not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ReferralRewardError as exc:
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ReferralPayoutRequestSerializer(req).data)
