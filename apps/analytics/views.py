"""
Admin analytics endpoints — financial, user, trading, exchange.
All endpoints require admin authentication.
"""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.bots.models import BotOrder, GridBot, SignalBot
from apps.payments.models import InvestorDeposit, WithdrawalRequest
from apps.subscriptions.models import TelegramSubscription

User = get_user_model()
logger = logging.getLogger("apps")


# ── Financial Analytics ──────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def financial_analytics(request):
    """
    GET /api/analytics/financial/
    Query params: days (default 30)
    Returns: revenue trend, withdrawal trend, net revenue, top depositors, currency breakdown.
    """
    try:
        days = int(request.query_params.get("days", 30))
        days = min(days, 365)
        start = timezone.now() - timedelta(days=days)

        # Revenue trend — daily approved deposits
        deposit_trend = (
            InvestorDeposit.objects.filter(status="approved", created_at__gte=start)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("date")
        )

        # Withdrawal trend — daily completed withdrawals
        withdrawal_trend = (
            WithdrawalRequest.objects.filter(status="completed", created_at__gte=start)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("date")
        )

        # Totals
        total_deposits = InvestorDeposit.objects.filter(
            status="approved", created_at__gte=start
        ).aggregate(total=Sum("amount"), count=Count("id"))
        total_withdrawals = WithdrawalRequest.objects.filter(
            status="completed", created_at__gte=start
        ).aggregate(total=Sum("amount"), count=Count("id"))

        deposit_total = float(total_deposits["total"] or 0)
        withdrawal_total = float(total_withdrawals["total"] or 0)

        # Top 10 depositors
        top_depositors = (
            InvestorDeposit.objects.filter(status="approved", created_at__gte=start)
            .values("user__id", "user__email")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")[:10]
        )

        # Currency breakdown
        currency_breakdown = (
            InvestorDeposit.objects.filter(status="approved", created_at__gte=start)
            .values("currency")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )

        return Response(
            {
                "period_days": days,
                "revenue": {
                    "total_deposits": deposit_total,
                    "total_deposit_count": total_deposits["count"],
                    "total_withdrawals": withdrawal_total,
                    "total_withdrawal_count": total_withdrawals["count"],
                    "net_revenue": deposit_total - withdrawal_total,
                },
                "deposit_trend": [
                    {"date": str(r["date"]), "total": float(r["total"]), "count": r["count"]}
                    for r in deposit_trend
                ],
                "withdrawal_trend": [
                    {"date": str(r["date"]), "total": float(r["total"]), "count": r["count"]}
                    for r in withdrawal_trend
                ],
                "top_depositors": [
                    {
                        "user_id": r["user__id"],
                        "email": r["user__email"],
                        "total": float(r["total"]),
                        "count": r["count"],
                    }
                    for r in top_depositors
                ],
                "currency_breakdown": [
                    {
                        "currency": r["currency"],
                        "total": float(r["total"]),
                        "count": r["count"],
                    }
                    for r in currency_breakdown
                ],
            }
        )
    except Exception as e:
        logger.error(f"financial_analytics error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load financial analytics"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── User Analytics ───────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def user_analytics(request):
    """
    GET /api/analytics/users/
    Query params: days (default 30)
    Returns: DAU/WAU/MAU, registration trend, subscription distribution.
    """
    try:
        days = int(request.query_params.get("days", 30))
        days = min(days, 365)
        now = timezone.now()
        start = now - timedelta(days=days)

        # DAU / WAU / MAU
        today = now.date()
        dau = User.objects.filter(last_login__date=today).count()
        wau = User.objects.filter(last_login__gte=now - timedelta(weeks=1)).count()
        mau = User.objects.filter(last_login__gte=now - timedelta(days=30)).count()

        # Registration trend — daily signups
        registration_trend = (
            User.objects.filter(date_joined__gte=start)
            .annotate(date=TruncDate("date_joined"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Subscription distribution (current)
        subscription_dist = (
            User.objects.values("subscription_plan").annotate(count=Count("id")).order_by("-count")
        )

        # Active subscriptions by plan
        active_subs = (
            TelegramSubscription.objects.filter(status="active")
            .values("plan__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # New users trend (last N days, cumulative)
        daily_signups = [{"date": str(r["date"]), "count": r["count"]} for r in registration_trend]

        return Response(
            {
                "period_days": days,
                "active_users": {"dau": dau, "wau": wau, "mau": mau},
                "registration_trend": daily_signups,
                "subscription_distribution": [
                    {"plan": r["subscription_plan"], "count": r["count"]} for r in subscription_dist
                ],
                "active_subscriptions": [
                    {"plan": r["plan__name"], "count": r["count"]} for r in active_subs
                ],
                "total_users": User.objects.count(),
            }
        )
    except Exception as e:
        logger.error(f"user_analytics error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load user analytics"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── Trading Analytics ────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def trading_analytics(request):
    """
    GET /api/analytics/trading/
    Query params: days (default 30)
    Returns: trade volume trend, strategy performance, top pairs, win/loss stats.
    """
    try:
        days = int(request.query_params.get("days", 30))
        days = min(days, 365)
        start = timezone.now() - timedelta(days=days)

        # Trade volume trend — daily order count + volume
        trade_trend = (
            BotOrder.objects.filter(created_at__gte=start)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                count=Count("id"),
                total_volume=Sum("Quantity"),
            )
            .order_by("date")
        )

        # Strategy breakdown — orders per bot type
        signal_count = BotOrder.objects.filter(
            signal_bot__isnull=False, created_at__gte=start
        ).count()
        grid_count = BotOrder.objects.filter(grid_bot__isnull=False, created_at__gte=start).count()
        martingale_count = BotOrder.objects.filter(
            martingale_bot__isnull=False, created_at__gte=start
        ).count()
        quantum_count = BotOrder.objects.filter(
            quantum_ai_investment__isnull=False, created_at__gte=start
        ).count()

        # Top pairs by order count
        top_pairs = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Pair")
            .annotate(count=Count("id"), volume=Sum("Quantity"))
            .order_by("-count")[:10]
        )

        # Top pairs by volume
        top_pairs_by_volume = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Pair")
            .annotate(volume=Sum("Quantity"), count=Count("id"))
            .order_by("-volume")[:10]
        )

        # Side distribution (buy vs sell)
        side_dist = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Side")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Order type distribution (market vs limit)
        order_type_dist = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Order_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Exchange distribution
        exchange_dist = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Exchange")
            .annotate(count=Count("id"), volume=Sum("Quantity"))
            .order_by("-count")
        )

        return Response(
            {
                "period_days": days,
                "total_orders": BotOrder.objects.filter(created_at__gte=start).count(),
                "trade_trend": [
                    {
                        "date": str(r["date"]),
                        "count": r["count"],
                        "volume": float(r["total_volume"] or 0),
                    }
                    for r in trade_trend
                ],
                "strategy_breakdown": {
                    "signal": signal_count,
                    "grid": grid_count,
                    "martingale": martingale_count,
                    "quantum_ai": quantum_count,
                },
                "top_pairs": [
                    {"pair": r["Pair"], "count": r["count"], "volume": float(r["volume"] or 0)}
                    for r in top_pairs
                ],
                "top_pairs_by_volume": [
                    {"pair": r["Pair"], "volume": float(r["volume"] or 0), "count": r["count"]}
                    for r in top_pairs_by_volume
                ],
                "side_distribution": [{"side": r["Side"], "count": r["count"]} for r in side_dist],
                "order_type_distribution": [
                    {"type": r["Order_type"], "count": r["count"]} for r in order_type_dist
                ],
                "exchange_distribution": [
                    {
                        "exchange": r["Exchange"],
                        "count": r["count"],
                        "volume": float(r["volume"] or 0),
                    }
                    for r in exchange_dist
                ],
            }
        )
    except Exception as e:
        logger.error(f"trading_analytics error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load trading analytics"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── Exchange Analytics ───────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def exchange_analytics(request):
    """
    GET /api/analytics/exchanges/
    Query params: days (default 30)
    Returns: volume per exchange, pair performance per exchange, exchange health.
    """
    try:
        days = int(request.query_params.get("days", 30))
        days = min(days, 365)
        start = timezone.now() - timedelta(days=days)

        # Volume per exchange
        exchange_volume = (
            BotOrder.objects.filter(created_at__gte=start)
            .values("Exchange")
            .annotate(
                total_orders=Count("id"),
                total_volume=Sum("Quantity"),
                avg_quantity=Avg("Quantity"),
            )
            .order_by("-total_volume")
        )

        # Pair performance per exchange — top pairs per exchange
        exchange_pairs = {}
        for ex in (
            BotOrder.objects.filter(created_at__gte=start)
            .values_list("Exchange", flat=True)
            .distinct()
        ):
            if not ex:
                continue
            pairs = (
                BotOrder.objects.filter(Exchange=ex, created_at__gte=start)
                .values("Pair")
                .annotate(count=Count("id"), volume=Sum("Quantity"))
                .order_by("-count")[:5]
            )
            exchange_pairs[ex] = [
                {"pair": r["Pair"], "count": r["count"], "volume": float(r["volume"] or 0)}
                for r in pairs
            ]

        # Bot count per exchange (active bots)
        active_bots_per_exchange = {}
        for ex_name, model, filter_field in [
            ("bybit", SignalBot, "exchange_name"),
            ("binance", SignalBot, "exchange_name"),
            ("okx", SignalBot, "exchange_name"),
            ("mexc", SignalBot, "exchange_name"),
            ("coinbase", SignalBot, "exchange_name"),
            ("alpaca", SignalBot, "exchange_name"),
        ]:
            count = SignalBot.objects.filter(**{filter_field: ex_name}, is_active=True).count()
            if count > 0:
                active_bots_per_exchange[ex_name] = count

        # Grid bots per exchange
        for ex_name in ["bybit", "binance", "okx"]:
            count = GridBot.objects.filter(exchange_name=ex_name, is_running=True).count()
            if count > 0:
                active_bots_per_exchange[f"{ex_name}_grid"] = count

        return Response(
            {
                "period_days": days,
                "exchange_volume": [
                    {
                        "exchange": r["Exchange"],
                        "total_orders": r["total_orders"],
                        "total_volume": float(r["total_volume"] or 0),
                        "avg_quantity": float(r["avg_quantity"] or 0),
                    }
                    for r in exchange_volume
                ],
                "exchange_pairs": exchange_pairs,
                "active_bots_per_exchange": active_bots_per_exchange,
            }
        )
    except Exception as e:
        logger.error(f"exchange_analytics error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load exchange analytics"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
