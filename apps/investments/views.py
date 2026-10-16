"""
Investment App Views for Torgovo Crypto Trading Platform
Portfolio/display views — orders, positions, balances, indicators, profile.
Bot CRUD and trading execution belong in apps.bots.
"""

import logging
from decimal import Decimal

import django_filters
from django.db.models import Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import InvestorLock, QuantumWithdrawalRequest
from services.quantum_locks import QuantumLockError, QuantumLockService

from .models import InvestmentBalance, Order, Position, TechnicalIndicator
from .serializers import (
    OrderSerializer,
    PositionSerializer,
    QuantumLockSerializer,
    QuantumWithdrawalRequestSerializer,
    TechnicalIndicatorSerializer,
    UserBalanceSerializer,
)

logger = logging.getLogger(__name__)


# ==================== PERMISSIONS ====================


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        try:
            if hasattr(obj, "user"):
                return obj.user == request.user
            elif hasattr(obj, "user_id"):
                return obj.user_id == request.user.id
            return False
        except Exception:
            return False


# ==================== PAGINATION ====================


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ==================== FILTERS ====================


class OrderFilter(django_filters.FilterSet):
    pair = django_filters.CharFilter(field_name="trading_pair__symbol", lookup_expr="iexact")
    exchange = django_filters.CharFilter(field_name="exchange__name")
    start_date = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    end_date = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Order
        fields = ["status", "side", "order_type"]


# ==================== VIEWSETS ====================


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).select_related(
            "exchange", "trading_pair"
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status == "pending":
            order.status = "cancelled"
            order.save()
            return Response({"status": "cancelled"})
        return Response({"error": "Cannot cancel this order"}, status=status.HTTP_400_BAD_REQUEST)


class PositionViewSet(viewsets.ModelViewSet):
    serializer_class = PositionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Position.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self.get_object()
        return Response({"status": "closed"})


class TechnicalIndicatorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TechnicalIndicator.objects.all()
    serializer_class = TechnicalIndicatorSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["indicator_type", "trading_pair", "exchange"]
    pagination_class = StandardResultsSetPagination


class UserBalanceViewSet(viewsets.ModelViewSet):
    serializer_class = UserBalanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return InvestmentBalance.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        balances = self.get_queryset()
        total_usdt = sum(balance.total for balance in balances if balance.currency == "USDT")
        return Response(
            {
                "total_usdt_value": total_usdt,
                "balances": UserBalanceSerializer(balances, many=True).data,
            }
        )


class UserOrdersView(APIView):
    """Get user's order history"""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        queryset = Order.objects.filter(user=request.user).select_related(
            "exchange", "trading_pair"
        )

        pair = request.query_params.get("pair")
        if pair:
            queryset = queryset.filter(trading_pair__symbol__iexact=pair)

        exchange = request.query_params.get("exchange")
        if exchange:
            queryset = queryset.filter(exchange__name=exchange)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        page = self.pagination_class()
        result_page = page.paginate_queryset(queryset, request)
        serializer = OrderSerializer(result_page, many=True)

        return page.get_paginated_response(serializer.data)


class UserProfileView(APIView):
    """Get user trading profile"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        max_bots = getattr(user, "max_bots_allowed", 10)
        total_trades = Order.objects.filter(user=user).count()
        total_volume = (
            Order.objects.filter(user=user).aggregate(total=Sum("quantity"))["total"] or 0
        )

        return Response(
            {
                "id": str(user.id),
                "user_email": user.email,
                "user_full_name": user.get_full_name(),
                "subscription_plan": user.subscription_plan,
                "max_bots_allowed": max_bots,
                "timezone": user.timezone,
                "demo_trading_enabled": user.demo_trading_enabled,
                "email_notifications": user.email_notifications,
                "is_subscription_active": user.is_subscription_active,
                "total_trades_executed": total_trades,
                "total_volume_traded": str(total_volume),
            }
        )


class BlockchainAddressesView(APIView):
    """
    Return the configured deposit addresses for Quantum AI.
    Only returns pre-provisioned addresses from apps.payments.BlockchainAddress.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.payments.models import BlockchainAddress

        addresses = {}
        for entry in BlockchainAddress.objects.filter(is_active=True):
            addresses.setdefault(entry.coin_type, {})[entry.blockchain] = entry.address
        if not addresses:
            return Response(
                {"error": "No deposit addresses configured. Contact support."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(addresses)


class InvestorDepositView(APIView):
    """Handle Quantum AI deposit submission (creates pending InvestorDeposit)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bot_id):
        from apps.bots.models import QuantumAIBot as BotsQuantumAIBot
        from apps.payments.models import InvestorDeposit

        try:
            BotsQuantumAIBot.objects.get(id=bot_id)
        except BotsQuantumAIBot.DoesNotExist:
            return Response({"error": "Bot not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            amount_raw = request.data.get("amount")
            coin_type = (request.data.get("coin_type") or "").upper().strip()
            blockchain = (request.data.get("blockchain") or "").upper().strip()
            transaction_hash = (request.data.get("transaction_hash") or "").strip()
            from_address = (request.data.get("from_address") or "").strip()
            screenshot = request.FILES.get("screenshot")

            if not all([amount_raw, coin_type, blockchain]):
                return Response(
                    {"error": "amount, coin_type and blockchain are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not transaction_hash and not screenshot:
                return Response(
                    {"error": "Provide a transaction hash or a screenshot"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                amount = Decimal(str(amount_raw))
            except Exception:
                return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)
            if amount <= 0:
                return Response({"error": "Amount must be > 0"}, status=status.HTTP_400_BAD_REQUEST)

            if (
                transaction_hash
                and InvestorDeposit.objects.filter(transaction_hash=transaction_hash).exists()
            ):
                return Response(
                    {"error": "Transaction hash already submitted"}, status=status.HTTP_409_CONFLICT
                )

            deposit = InvestorDeposit.objects.create(
                user=request.user,
                amount=amount,
                currency=coin_type,
                blockchain=blockchain,
                from_address=from_address,
                transaction_hash=transaction_hash,
                transaction_screenshot=screenshot,
                status="pending",
            )
            return Response(
                {
                    "message": "Deposit submitted for review",
                    "deposit_id": str(deposit.id),
                    "status": deposit.status,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Quantum AI deposit error: {str(e)}")
            return Response(
                {"error": "Deposit failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============ A5 QUANTUM AI LOCKS (G3 — FUNCTIONAL_REQUIREMENTS.md §A5) ============
# User surface: list own locks + file post-lock withdrawal requests.
# Admin surface: credit matured locks (free-form %) + decide withdrawal
# requests (approve requires the payout amount incl. chain fees — grill Q12).


def _paginate_lock_queryset(qs, request):
    """Minimal page/page_size pagination (50 default, 200 cap)."""
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get("page_size", 50))
    except (TypeError, ValueError):
        page_size = 50
    page_size = max(1, min(page_size, 200))

    total = qs.count()
    start = (page - 1) * page_size
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": qs[start : start + page_size],
    }


class QuantumLockListView(APIView):
    """GET own locks (staff: all locks). Filters: ?status=, ?matured=1."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = InvestorLock.objects.select_related("fund", "user").order_by("-created_at")
        if not request.user.is_staff:
            qs = qs.filter(user=request.user)

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        if request.query_params.get("matured"):  # admin "ready to credit" queue
            from django.utils import timezone as _tz

            qs = qs.filter(matures_at__lte=_tz.now())

        payload = _paginate_lock_queryset(qs, request)
        payload["results"] = QuantumLockSerializer(payload["results"], many=True).data
        return Response(payload)


class QuantumLockWithdrawView(APIView):
    """POST file a withdrawal request against a matured lock (owner only)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lock_id):
        try:
            amount_raw = request.data.get("amount")
            if amount_raw is None:
                return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                amount = Decimal(str(amount_raw))
            except Exception:
                return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

            withdrawal = QuantumLockService.request_withdrawal(
                user=request.user, lock_id=lock_id, amount=amount
            )
            return Response(
                QuantumWithdrawalRequestSerializer(withdrawal).data,
                status=status.HTTP_201_CREATED,
            )
        except InvestorLock.DoesNotExist:
            # Service raises this for non-owner access too — no existence leak.
            return Response({"error": "Lock not found"}, status=status.HTTP_404_NOT_FOUND)
        except QuantumLockError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class QuantumLockCreditView(APIView):
    """POST admin: credit a matured lock by `pct` (capital x (1 + pct/100))."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, lock_id):
        try:
            pct_raw = request.data.get("pct")
            if pct_raw is None:
                return Response({"error": "pct is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                pct = Decimal(str(pct_raw))
            except Exception:
                return Response({"error": "Invalid pct"}, status=status.HTTP_400_BAD_REQUEST)

            credit = QuantumLockService.credit_maturity(
                lock_id=lock_id, pct=pct, admin=request.user
            )
            return Response(
                {
                    "credit_id": str(credit.id),
                    "term_number": credit.term_number,  # term that was credited
                    "current_term": credit.lock.term_number,  # term now running
                    "pct_entered": str(credit.pct_entered),
                    "profit_amount": str(credit.profit_amount),
                    "capital_after": str(credit.capital_after),
                },
                status=status.HTTP_201_CREATED,
            )
        except InvestorLock.DoesNotExist:
            return Response({"error": "Lock not found"}, status=status.HTTP_404_NOT_FOUND)
        except QuantumLockError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class QuantumWithdrawalRequestListView(APIView):
    """GET own withdrawal requests (staff: all; ?status=pending filter)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = QuantumWithdrawalRequest.objects.select_related("user", "lock").order_by(
            "-requested_at"
        )
        if not request.user.is_staff:
            qs = qs.filter(user=request.user)

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        payload = _paginate_lock_queryset(qs, request)
        payload["results"] = QuantumWithdrawalRequestSerializer(payload["results"], many=True).data
        return Response(payload)


class QuantumWithdrawalDecisionView(APIView):
    """
    POST admin decides a pending request:
      {"action": "approve", "payout_amount": ..., "notes": "..."}  # incl. fees
      {"action": "reject", "notes": "..."}
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, request_id):
        action = (request.data.get("action") or "").strip().lower()
        notes = str(request.data.get("notes") or "")

        try:
            if action == "approve":
                payout_raw = request.data.get("payout_amount")
                if payout_raw is None:
                    return Response(
                        {"error": "payout_amount is required for approval (incl. chain fees)"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    payout_amount = Decimal(str(payout_raw))
                except Exception:
                    return Response(
                        {"error": "Invalid payout_amount"}, status=status.HTTP_400_BAD_REQUEST
                    )
                updated = QuantumLockService.approve_withdrawal(
                    request_id=request_id,
                    admin=request.user,
                    payout_amount=payout_amount,
                    notes=notes,
                )
            elif action == "reject":
                updated = QuantumLockService.reject_withdrawal(
                    request_id=request_id, admin=request.user, notes=notes
                )
            else:
                return Response(
                    {"error": "action must be 'approve' or 'reject'"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(QuantumWithdrawalRequestSerializer(updated).data)
        except QuantumWithdrawalRequest.DoesNotExist:
            return Response({"error": "Request not found"}, status=status.HTTP_404_NOT_FOUND)
        except QuantumLockError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
