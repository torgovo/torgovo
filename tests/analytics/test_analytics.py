"""
Tests for admin analytics endpoints.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status

User = get_user_model()


# ---------------------------------------------------------------------------
# Financial Analytics
# ---------------------------------------------------------------------------


class TestFinancialAnalytics:
    url = "/api/analytics/financial/"

    def test_as_admin(self, admin_client, user):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "revenue" in response.data
        assert "deposit_trend" in response.data
        assert "withdrawal_trend" in response.data
        assert "top_depositors" in response.data
        assert "currency_breakdown" in response.data

    def test_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_default_period(self, admin_client):
        response = admin_client.get(self.url)
        assert response.data["period_days"] == 30

    def test_custom_period(self, admin_client):
        response = admin_client.get(self.url, {"days": "60"})
        assert response.data["period_days"] == 60

    def test_period_capped_at_365(self, admin_client):
        response = admin_client.get(self.url, {"days": "999"})
        assert response.data["period_days"] == 365

    def test_revenue_totals_zero_with_no_data(self, admin_client):
        response = admin_client.get(self.url)
        revenue = response.data["revenue"]
        assert revenue["total_deposits"] == 0
        assert revenue["total_withdrawals"] == 0
        assert revenue["net_revenue"] == 0

    def test_with_deposit_data(self, admin_client, user):
        from apps.payments.models import InvestorDeposit

        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("500.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0xsender",
            transaction_hash="0xabc111",
            status="approved",
        )
        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("250.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0xsender",
            transaction_hash="0xdef222",
            status="approved",
        )
        response = admin_client.get(self.url)
        revenue = response.data["revenue"]
        assert revenue["total_deposits"] == 750.0
        assert revenue["total_deposit_count"] == 2
        assert revenue["net_revenue"] == 750.0

    def test_with_withdrawal_data(self, admin_client, user):
        from apps.payments.models import WithdrawalRequest

        WithdrawalRequest.objects.create(
            user=user,
            amount=Decimal("100.00"),
            currency="USDT",
            blockchain="ERC20",
            to_address="0xwallet",
            total_amount=Decimal("100.00"),
            status="completed",
        )
        response = admin_client.get(self.url)
        revenue = response.data["revenue"]
        assert revenue["total_withdrawals"] == 100.0
        assert revenue["net_revenue"] == -100.0

    def test_pending_deposits_excluded(self, admin_client, user):
        from apps.payments.models import InvestorDeposit

        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("500.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0xsender",
            transaction_hash="0xpending111",
            status="pending",
        )
        response = admin_client.get(self.url)
        assert response.data["revenue"]["total_deposits"] == 0

    def test_top_depositors_ordering(self, admin_client, user, second_user):
        from apps.payments.models import InvestorDeposit

        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("100.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0x1",
            transaction_hash="0xtx1",
            status="approved",
        )
        InvestorDeposit.objects.create(
            user=second_user,
            amount=Decimal("500.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0x2",
            transaction_hash="0xtx2",
            status="approved",
        )
        response = admin_client.get(self.url)
        depositors = response.data["top_depositors"]
        assert len(depositors) == 2
        assert depositors[0]["total"] == 500.0
        assert depositors[1]["total"] == 100.0

    def test_currency_breakdown(self, admin_client, user):
        from apps.payments.models import InvestorDeposit

        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("100.00"),
            currency="USDT",
            blockchain="ERC20",
            from_address="0x1",
            transaction_hash="0xcur1",
            status="approved",
        )
        InvestorDeposit.objects.create(
            user=user,
            amount=Decimal("2.00"),
            currency="ETH",
            blockchain="ERC20",
            from_address="0x1",
            transaction_hash="0xcur2",
            status="approved",
        )
        response = admin_client.get(self.url)
        breakdown = {r["currency"]: r for r in response.data["currency_breakdown"]}
        assert breakdown["USDT"]["total"] == 100.0
        assert breakdown["ETH"]["total"] == 2.0


# ---------------------------------------------------------------------------
# User Analytics
# ---------------------------------------------------------------------------


class TestUserAnalytics:
    url = "/api/analytics/users/"

    def test_as_admin(self, admin_client, user):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "active_users" in response.data
        assert "registration_trend" in response.data
        assert "subscription_distribution" in response.data
        assert "total_users" in response.data

    def test_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_active_users_counts(self, admin_client, user, admin_user):
        from django.utils import timezone as _tz

        now = _tz.now()
        User.objects.filter(pk=user.pk).update(last_login=now)
        User.objects.filter(pk=admin_user.pk).update(last_login=now)
        response = admin_client.get(self.url)
        active = response.data["active_users"]
        assert active["mau"] >= 1
        assert active["wau"] >= 1
        assert active["dau"] >= 1

    def test_total_users(self, admin_client, user, admin_user):
        response = admin_client.get(self.url)
        assert response.data["total_users"] >= 2

    def test_subscription_distribution(self, admin_client, user):
        response = admin_client.get(self.url)
        dist = response.data["subscription_distribution"]
        assert isinstance(dist, list)
        plans = [d["plan"] for d in dist]
        assert "free" in plans

    def test_registration_trend(self, admin_client, user):
        response = admin_client.get(self.url)
        trend = response.data["registration_trend"]
        assert isinstance(trend, list)
        assert len(trend) >= 1
        assert "date" in trend[0]
        assert "count" in trend[0]

    def test_custom_period(self, admin_client):
        response = admin_client.get(self.url, {"days": "7"})
        assert response.data["period_days"] == 7


# ---------------------------------------------------------------------------
# Trading Analytics
# ---------------------------------------------------------------------------


class TestTradingAnalytics:
    url = "/api/analytics/trading/"

    def test_as_admin(self, admin_client):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "total_orders" in response.data
        assert "trade_trend" in response.data
        assert "strategy_breakdown" in response.data
        assert "top_pairs" in response.data
        assert "side_distribution" in response.data
        assert "order_type_distribution" in response.data
        assert "exchange_distribution" in response.data

    def test_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_empty_data(self, admin_client):
        response = admin_client.get(self.url)
        assert response.data["total_orders"] == 0
        assert response.data["strategy_breakdown"]["signal"] == 0
        assert response.data["strategy_breakdown"]["grid"] == 0

    def test_with_bot_orders(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.1"),
            Price=Decimal("50000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="ETH/USDT",
            Side="sell",
            Order_type="limit",
            Quantity=Decimal("1.0"),
            Price=Decimal("3000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        assert response.data["total_orders"] == 2
        assert response.data["strategy_breakdown"]["signal"] == 2

    def test_side_distribution(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        for side in ["buy", "buy", "sell"]:
            BotOrder.objects.create(
                user=user,
                signal_bot=signal_bot,
                Pair="BTC/USDT",
                Side=side,
                Order_type="market",
                Quantity=Decimal("0.1"),
                Price=Decimal("50000"),
                Exchange="binance",
                Time=timezone.now(),
            )
        response = admin_client.get(self.url)
        sides = {r["side"]: r["count"] for r in response.data["side_distribution"]}
        assert sides["buy"] == 2
        assert sides["sell"] == 1

    def test_exchange_distribution(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.1"),
            Price=Decimal("50000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        exch = {r["exchange"]: r for r in response.data["exchange_distribution"]}
        assert "binance" in exch
        assert exch["binance"]["count"] == 1

    def test_top_pairs(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        for i in range(5):
            BotOrder.objects.create(
                user=user,
                signal_bot=signal_bot,
                Pair="BTC/USDT",
                Side="buy",
                Order_type="market",
                Quantity=Decimal("0.1"),
                Price=Decimal("50000"),
                Exchange="binance",
                Time=timezone.now(),
            )
        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="ETH/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("1.0"),
            Price=Decimal("3000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        pairs = response.data["top_pairs"]
        assert pairs[0]["pair"] == "BTC/USDT"
        assert pairs[0]["count"] == 5


# ---------------------------------------------------------------------------
# Exchange Analytics
# ---------------------------------------------------------------------------


class TestExchangeAnalytics:
    url = "/api/analytics/exchanges/"

    def test_as_admin(self, admin_client):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "exchange_volume" in response.data
        assert "exchange_pairs" in response.data
        assert "active_bots_per_exchange" in response.data

    def test_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_empty_data(self, admin_client):
        response = admin_client.get(self.url)
        assert response.data["exchange_volume"] == []

    def test_with_data(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.5"),
            Price=Decimal("50000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="ETH/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("2.0"),
            Price=Decimal("3000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        vol = response.data["exchange_volume"]
        assert len(vol) == 1
        assert vol[0]["exchange"] == "binance"
        assert vol[0]["total_orders"] == 2
        assert float(vol[0]["total_volume"]) == 2.5

    def test_exchange_pairs_breakdown(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.1"),
            Price=Decimal("50000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="ETH/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("1.0"),
            Price=Decimal("3000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        pairs = response.data["exchange_pairs"]
        assert "binance" in pairs
        assert len(pairs["binance"]) == 2

    def test_multi_exchange(self, admin_client, user, signal_bot):
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.1"),
            Price=Decimal("50000"),
            Exchange="binance",
            Time=timezone.now(),
        )
        BotOrder.objects.create(
            user=user,
            signal_bot=signal_bot,
            Pair="BTC/USDT",
            Side="buy",
            Order_type="market",
            Quantity=Decimal("0.1"),
            Price=Decimal("50000"),
            Exchange="bybit",
            Time=timezone.now(),
        )
        response = admin_client.get(self.url)
        vol = {r["exchange"]: r for r in response.data["exchange_volume"]}
        assert "binance" in vol
        assert "bybit" in vol
