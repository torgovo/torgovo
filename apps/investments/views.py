"""
Investment App Views for Torgovo Crypto Trading Platform
Portfolio/display views — orders, positions, balances, indicators, profile.
Bot CRUD and trading execution belong in apps.bots.
"""

import hmac as _hmac
import logging
from decimal import Decimal

import django_filters
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exchanges.models import Exchange, TradingPair

from .models import InvestmentBalance, Order, Position, TechnicalIndicator
from .serializers import (
    OrderSerializer,
    PositionSerializer,
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


# ==================== WEBHOOK HANDLERS ====================


class TradingViewWebhookView(APIView):
    """
    Handle TradingView webhook alerts. Looks up the bot by webhook_id
    on apps.bots.SignalBot (the real webhook bot model), validates via
    constant-time HMAC, and records the order in the investments Order model.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "webhook"

    def post(self, request, webhook_id):
        from apps.bots.models import SignalBot

        try:
            bot = SignalBot.objects.get(bot_id=webhook_id, is_active=True)

            # Verify secret key in constant time
            secret = str(request.data.get("secret", ""))
            expected = str(bot.secret_key or "")
            if not expected or not _hmac.compare_digest(secret, expected):
                logger.warning(f"Invalid webhook secret for {webhook_id}")
                return Response({"error": "Invalid secret key"}, status=status.HTTP_403_FORBIDDEN)

            # Process the trade
            action = request.data.get("action", "").lower()
            amount = Decimal(str(request.data.get("order", {}).get("amount", bot.default_amount)))

            if action in ["buy", "sell"]:
                self.execute_trade(bot, action, amount, request.data)
                bot.last_triggered = timezone.now()
                bot.save()

                return Response(
                    {
                        "status": "success",
                        "message": f"Webhook processed: {action} {amount} {bot.trading_pair}",
                        "bot_id": str(bot.id),
                    }
                )

            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        except SignalBot.DoesNotExist:
            return Response({"error": "Bot not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return Response(
                {"error": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def execute_trade(self, bot, action, amount, data):
        with db_transaction.atomic():
            Order.objects.create(
                user=bot.user,
                exchange=Exchange.objects.filter(name=bot.exchange_name).first(),
                trading_pair=TradingPair.objects.filter(symbol=bot.trading_pair).first(),
                order_type="market",
                side=action,
                quantity=amount,
                price=Decimal("0"),
                description=f"TradingView webhook: {data.get('strategy_info', {})}",
            )
            bot.total_trades += 1
            bot.save()


class EMAWebhookView(APIView):
    """
    Handle EMA indicator webhooks. Restricted to staff/admin.
    Stores indicator in TechnicalIndicator model.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        try:
            data = request.data
            pair = data.get("pair")
            exchange_name = data.get("exchange")
            ema_value = data.get("EMA200")

            exchange = get_object_or_404(Exchange, name=exchange_name)
            trading_pair = get_object_or_404(TradingPair, symbol=pair, exchange_name=exchange_name)

            TechnicalIndicator.objects.create(
                indicator_type="EMA",
                trading_pair=trading_pair,
                exchange=exchange,
                values={"EMA200": ema_value},
                triggered_at=timezone.now(),
            )

            return Response(
                {"status": "success", "message": f"EMA processed for {pair}", "EMA": ema_value}
            )

        except Http404:
            raise
        except Exception as e:
            logger.error(f"EMA webhook error: {str(e)}", exc_info=True)
            return Response(
                {"error": "An internal error occurred"}, status=status.HTTP_400_BAD_REQUEST
            )


class RSIWebhookView(APIView):
    """
    Handle RSI indicator webhooks. Restricted to staff/admin.
    Stores indicator in TechnicalIndicator model.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        try:
            data = request.data
            pair = data.get("pair")
            exchange_name = data.get("exchange")
            rsi_value = float(data.get("RSI", 0))
            color = data.get("color")
            prev_color = data.get("prev_color")

            exchange = get_object_or_404(Exchange, name=exchange_name)
            trading_pair = get_object_or_404(TradingPair, symbol=pair, exchange_name=exchange_name)

            prev_rsi = data.get("PrevRSI")
            TechnicalIndicator.objects.create(
                indicator_type="RSI",
                trading_pair=trading_pair,
                exchange=exchange,
                values={"RSI": rsi_value, "PrevRSI": prev_rsi},
                color=color,
                prev_color=prev_color,
                triggered_at=timezone.now(),
            )

            return Response(
                {"status": "success", "message": f"RSI processed for {pair}", "RSI": rsi_value}
            )

        except Http404:
            raise
        except Exception as e:
            logger.error(f"RSI webhook error: {str(e)}", exc_info=True)
            return Response(
                {"error": "An internal error occurred"}, status=status.HTTP_400_BAD_REQUEST
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


class QuantumAIDepositView(APIView):
    """Handle Quantum AI deposit submission (creates pending QuantumAIDeposit)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bot_id):
        from apps.bots.models import QuantumAIBot as BotsQuantumAIBot
        from apps.payments.models import QuantumAIDeposit

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
                and QuantumAIDeposit.objects.filter(transaction_hash=transaction_hash).exists()
            ):
                return Response(
                    {"error": "Transaction hash already submitted"}, status=status.HTTP_409_CONFLICT
                )

            deposit = QuantumAIDeposit.objects.create(
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
