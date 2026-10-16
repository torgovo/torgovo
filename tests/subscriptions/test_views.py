import base64
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.subscriptions.models import (
    SignalResult,
    TelegramChannel,
    TelegramSignalPlan,
    TelegramSubscription,
    TradingSignal,
)


@pytest.mark.django_db
class TestTelegramSignalPlanViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = TelegramSignalPlan.objects.create(
            name="Premium",
            slug="premium",
            description="Premium signals",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        TelegramSignalPlan.objects.create(
            name="Inactive",
            slug="inactive",
            description="Inactive",
            price_monthly=0,
            price_quarterly=0,
            price_yearly=0,
            is_active=False,
        )

    def test_list_active_plans(self, auth_client):
        url = reverse("subscriptions:plans-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_retrieve_plan(self, auth_client):
        url = reverse("subscriptions:plans-detail", args=[self.plan.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Premium"

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:plans-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramSubscriptionViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro signals",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        self.sub = TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
        )

    def test_list_subscriptions(self, auth_client):
        url = reverse("subscriptions:subscriptions-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_retrieve_subscription(self, auth_client):
        url = reverse("subscriptions:subscriptions-detail", args=[self.sub.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_other_user_subscriptions_not_visible(self, auth_client, user, admin_user):
        TelegramSubscription.objects.create(
            user=admin_user,
            plan=self.plan,
            telegram_handle="tg_admin",
            amount_paid=Decimal("49.99"),
        )
        url = reverse("subscriptions:subscriptions-list")
        response = auth_client.get(url)
        assert len(response.data["results"]) == 1

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:subscriptions-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramChannelViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramChannel.objects.create(
            name="Signals",
            channel_id="signals_ch",
            channel_type="signals",
            invite_link="https://t.me/signals_ch",
            description="Signals",
            is_active=True,
        )
        TelegramChannel.objects.create(
            name="Hidden",
            channel_id="hidden_ch",
            channel_type="analysis",
            invite_link="https://t.me/hidden_ch",
            description="Hidden",
            is_active=False,
        )

    def test_list_active_channels(self, auth_client):
        url = reverse("subscriptions:channels-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:channels-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTradingSignalViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.user = user
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Premium signals",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        self.other_plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic signals",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        self.signal = TradingSignal.objects.create(
            plan=self.plan,
            signal_type="buy",
            trading_pair="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            entry_price=Decimal("50000"),
            analysis="Test",
            published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        # A12: the list is scoped to active subscription plans — the owner
        # of this fixture needs an active sub to see their plan's signal.
        TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )

    def test_list_active_signals(self, auth_client):
        url = reverse("subscriptions:signals-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:signals-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_subscription_sees_no_signals(self, second_auth_client):
        """A12: authenticated but no subscription -> empty list."""
        url = reverse("subscriptions:signals-list")
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_other_plan_subscription_scoped_out(self, db, second_user, second_auth_client):
        """A12: active sub to a DIFFERENT plan must not leak signals."""
        TelegramSubscription.objects.create(
            user=second_user,
            plan=self.other_plan,
            telegram_handle="tg_other",
            amount_paid=Decimal("9.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse("subscriptions:signals-list")
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_expired_subscription_scoped_out(self, auth_client):
        """A12: status=active but end_date in the past = no access."""
        sub = TelegramSubscription.objects.get(user=self.user)
        sub.end_date = timezone.now().date() - timezone.timedelta(days=1)
        sub.save()
        url = reverse("subscriptions:signals-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_detail_scoped_out_returns_404(self, second_auth_client):
        """A12: cross-plan detail fetch must not leak (404, not 200)."""
        url = reverse("subscriptions:signals-detail", args=[self.signal.id])
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_visible_to_subscriber(self, auth_client):
        url = reverse("subscriptions:signals-detail", args=[self.signal.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(self.signal.id)


@pytest.mark.django_db
class TestSignalResultViewSet:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.user = user
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Premium signals",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        self.other_plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic signals",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        self.signal = TradingSignal.objects.create(
            plan=self.plan,
            signal_type="buy",
            trading_pair="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            entry_price=Decimal("50000"),
            analysis="Test",
            published_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        self.result = SignalResult.objects.create(
            signal=self.signal,
            result_type="profit",
            entry_price_actual=Decimal("50000"),
            profit_loss=Decimal("1000"),
            profit_loss_percent=Decimal("2.00"),
            entry_time=timezone.now(),
        )
        # A12: scope results to active subscription plans
        TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )

    def test_list_results(self, auth_client):
        url = reverse("subscriptions:signal-results-list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:signal-results-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_subscription_sees_no_results(self, second_auth_client):
        """A12: results are plan-scoped too — no sub, no results."""
        url = reverse("subscriptions:signal-results-list")
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_other_plan_subscription_scoped_out(self, second_user, second_auth_client):
        """A12: active sub to a DIFFERENT plan must not leak results."""
        TelegramSubscription.objects.create(
            user=second_user,
            plan=self.other_plan,
            telegram_handle="tg_other",
            amount_paid=Decimal("9.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse("subscriptions:signal-results-list")
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_detail_scoped_out_returns_404(self, second_auth_client):
        url = reverse("subscriptions:signal-results-detail", args=[self.result.id])
        response = second_auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_visible_to_subscriber(self, auth_client):
        url = reverse("subscriptions:signal-results-detail", args=[self.result.id])
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(self.result.id)


@pytest.mark.django_db
class TestPublicPlanListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramSignalPlan.objects.create(
            name="Public Plan",
            slug="public",
            description="Public",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=199.99,
        )

    def test_public_list(self, api_client):
        url = reverse("subscriptions:public_plans")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestMySubscriptionView:
    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.plan = TelegramSignalPlan.objects.create(
            name="Active Plan",
            slug="active-plan",
            description="Active",
            price_monthly=29.99,
            price_quarterly=79.99,
            price_yearly=299.99,
        )

    def test_no_active_subscription(self, auth_client):
        # A8: no more 404 {"message": ...} — always 200, null body when empty
        url = reverse("subscriptions:my_subscription")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["subscription"] is None

    def test_pending_approval_is_visible(self, auth_client, user):
        # A8: pending states surface on my-subscription (previously 404)
        TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_pending",
            amount_paid=Decimal("29.99"),
            status="pending_approval",
        )
        url = reverse("subscriptions:my_subscription")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "pending_approval"

    def test_with_active_subscription(self, auth_client, user):
        TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_active",
            amount_paid=Decimal("29.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse("subscriptions:my_subscription")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "active"

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:my_subscription")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAdminChannelViews:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramChannel.objects.create(
            name="Channel 1",
            channel_id="ch1",
            channel_type="signals",
            invite_link="https://t.me/ch1",
            description="Ch1",
        )

    def test_admin_list_channels(self, admin_client):
        url = reverse("subscriptions:admin_channel_list")
        response = admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_admin_create_channel(self, admin_client):
        url = reverse("subscriptions:admin_create_channel")
        data = {
            "name": "New Channel",
            "channel_id": "new_ch",
            "channel_type": "analysis",
            "invite_link": "https://t.me/new_ch",
            "description": "New analysis channel",
        }
        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_non_admin_cannot_list_channels(self, auth_client):
        url = reverse("subscriptions:admin_channel_list")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_admin_cannot_create_channel(self, auth_client):
        url = reverse("subscriptions:admin_create_channel")
        data = {
            "name": "Test",
            "channel_id": "test_ch",
            "channel_type": "signals",
            "invite_link": "https://t.me/test",
            "description": "Test",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTelegramPlanListView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        TelegramSignalPlan.objects.create(
            name="Telegram Pro",
            slug="tg-pro",
            description="TG Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )

    def test_public_telegram_plans(self, api_client):
        url = reverse("subscriptions:telegram-plan-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "plans" in response.data

    def test_cached_response(self, api_client):
        url = reverse("subscriptions:telegram-plan-list")
        response1 = api_client.get(url)
        response2 = api_client.get(url)
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestMyTelegramUsageView:
    def test_no_active_subscription(self, auth_client):
        url = reverse("subscriptions:telegram-my-usage")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is False

    def test_with_active_subscription(self, auth_client, user):
        plan = TelegramSignalPlan.objects.create(
            name="Usage Plan",
            slug="usage-plan",
            description="Usage",
            price_monthly=29.99,
            price_quarterly=79.99,
            price_yearly=299.99,
            signals_per_day=15,
            exchanges_covered=["binance"],
        )
        TelegramSubscription.objects.create(
            user=user,
            plan=plan,
            telegram_handle="tg_usage",
            amount_paid=Decimal("29.99"),
            status="active",
            end_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        url = reverse("subscriptions:telegram-my-usage")
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True
        assert response.data["plan"] == "Usage Plan"

    def test_unauthenticated(self, api_client):
        url = reverse("subscriptions:telegram-my-usage")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTelegramSubscribeView:
    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = TelegramSignalPlan.objects.create(
            name="Subscribe Plan",
            slug="sub-plan",
            description="Subscribe",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )

    def test_subscribe_success(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        data = {
            "plan_id": str(self.plan.id),
            "telegram_handle": "new_user_tg",
            "payment_transaction_hash": "0xtx_subscribe_success",
            "payment_blockchain": "BEP20",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "pending_approval"

    def test_subscribe_missing_fields(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_missing_handle(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        data = {"plan_id": str(self.plan.id)}
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_invalid_plan(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        data = {
            "plan_id": "00000000-0000-0000-0000-000000000000",
            "telegram_handle": "tg_user",
            "payment_transaction_hash": "0xhash",
        }
        response = auth_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_subscribe_unauthenticated(self, api_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPlanListView:
    def test_lists_active_plans(self, api_client):
        from apps.payments.models import SubscriptionPlan

        SubscriptionPlan.objects.create(
            name="Free",
            slug="free",
            price_monthly="0",
            price_yearly="0",
            max_bots_allowed=1,
            max_webhooks_allowed=10,
            is_active=True,
        )
        SubscriptionPlan.objects.create(
            name="Premium",
            slug="premium",
            price_monthly="29.99",
            price_yearly="299.99",
            max_bots_allowed=10,
            max_webhooks_allowed=100,
            is_active=True,
        )
        SubscriptionPlan.objects.create(
            name="Inactive",
            slug="inactive",
            price_monthly="99.99",
            price_yearly="999.99",
            max_bots_allowed=50,
            max_webhooks_allowed=500,
            is_active=False,
        )
        url = reverse("subscriptions:plan-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data["plans"]) == 2
        names = [p["name"] for p in response.data["plans"]]
        assert "Free" in names
        assert "Premium" in names
        assert "Inactive" not in names

    def test_returns_prices_as_strings(self, api_client):
        from apps.payments.models import SubscriptionPlan

        SubscriptionPlan.objects.create(
            name="Pro",
            slug="pro",
            price_monthly="49.99",
            price_yearly="499.99",
            max_bots_allowed=20,
            max_webhooks_allowed=200,
            is_active=True,
        )
        url = reverse("subscriptions:plan-list")
        response = api_client.get(url)
        assert response.data["plans"][0]["price_monthly"] == "49.99"
        assert response.data["plans"][0]["price_yearly"] == "499.99"


@pytest.mark.django_db
class TestSubscribeView:
    def _create_user(self):
        from apps.users.models import CustomUser

        return CustomUser.objects.create_user("test@t.com", "test@t.com", "pass")

    def test_subscribe_creates_subscription(self, api_client):
        from apps.payments.models import SubscriptionPlan

        user = self._create_user()
        api_client.force_authenticate(user)
        SubscriptionPlan.objects.create(
            name="Premium",
            slug="premium",
            price_monthly="29.99",
            price_yearly="299.99",
            max_bots_allowed=10,
            max_webhooks_allowed=100,
            is_active=True,
        )
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": "premium"}, format="json")
        assert response.status_code == 201
        assert response.data["status"] == "pending_payment"

    def test_missing_plan_id_returns_400(self, api_client):
        user = self._create_user()
        api_client.force_authenticate(user)
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {}, format="json")
        assert response.status_code == 400

    def test_invalid_plan_id_returns_400(self, api_client):
        user = self._create_user()
        api_client.force_authenticate(user)
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": "nonexistent"}, format="json")
        assert response.status_code == 400

    def test_duplicate_subscription_returns_409(self, api_client):
        from apps.payments.models import BotSubscription, BotSubscriptionPlan, SubscriptionPlan

        user = self._create_user()
        api_client.force_authenticate(user)
        SubscriptionPlan.objects.create(
            name="Premium",
            slug="premium",
            price_monthly="29.99",
            price_yearly="299.99",
            max_bots_allowed=10,
            max_webhooks_allowed=100,
            is_active=True,
        )
        bot_plan = BotSubscriptionPlan.objects.create(
            name="Premium",
            bot_type="custom",
            price="29.99",
        )
        BotSubscription.objects.create(user=user, plan=bot_plan, status="pending_payment")
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": "premium"}, format="json")
        assert response.status_code == 409

    def test_unauthenticated_returns_401(self, api_client):
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": 1}, format="json")
        assert response.status_code == 401


@pytest.mark.django_db
class TestMyUsageView:
    def _create_user(self):
        from apps.users.models import CustomUser

        return CustomUser.objects.create_user("test@t.com", "test@t.com", "pass")

    def test_returns_usage_with_active_subscription(self, api_client):
        from apps.payments.models import BotSubscription, BotSubscriptionPlan

        user = self._create_user()
        api_client.force_authenticate(user)
        bot_plan = BotSubscriptionPlan.objects.create(
            name="Premium",
            bot_type="custom",
            price="29.99",
            features={"max_bots": 10, "max_webhooks": 100},
            duration_days=30,
        )
        BotSubscription.objects.create(user=user, plan=bot_plan, status="active")
        url = reverse("subscriptions:my-usage")
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["plan"]["name"] == "Premium"

    def test_no_subscription_returns_empty(self, api_client):
        user = self._create_user()
        api_client.force_authenticate(user)
        url = reverse("subscriptions:my-usage")
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["plan"] is None
        assert response.data["status"] is None

    def test_unauthenticated_returns_401(self, api_client):
        url = reverse("subscriptions:my-usage")
        response = api_client.get(url)
        assert response.status_code == 401


# ============================================================================
# A11 — sensitive fields are read-only on subscriptions CRUD
# ============================================================================


@pytest.mark.django_db
class TestSubscriptionWriteSurface:
    """A11: status, billing, admin and soft-delete fields must not be
    user-writable; channels are assigned server-side on approval."""

    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.user = user
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        self.channel = TelegramChannel.objects.create(
            name="Signals",
            channel_id="signals_ch",
            channel_type="signals",
            invite_link="https://t.me/signals_ch",
            description="Signals",
            is_active=True,
            required_plan=None,
        )
        self.sub = TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
            status="pending_payment",
        )

    def test_create_ignores_sensitive_fields(self, auth_client):
        """POST must ignore status/billing/admin/soft-delete/channels payload keys."""
        url = reverse("subscriptions:subscriptions-list")
        payload = {
            "plan": self.plan.id,
            "telegram_handle": "tg_new",
            "status": "active",
            "admin_notes": "self-approve",
            "rejection_reason": "n/a",
            "billing_cycle": "yearly",
            "payment_method": "stripe",
            "stripe_subscription_id": "sub_123",
            "auto_renew": False,
            "success_rate_tracked": 100,
            "telegram_user_id": 999888,
            "is_deleted": True,
            "channels": [self.channel.id],
            "amount_paid": 0.01,
        }
        response = auth_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        sub = TelegramSubscription.objects.get(telegram_handle="tg_new")
        assert sub.status == "pending_payment"  # not "active"
        assert sub.admin_notes == ""
        assert sub.rejection_reason == ""
        assert sub.billing_cycle == "monthly"
        assert sub.payment_method == "crypto"
        assert sub.stripe_subscription_id == ""
        assert sub.auto_renew is True
        assert sub.success_rate_tracked == Decimal("0.00")
        assert sub.telegram_user_id is None
        assert sub.is_deleted is False
        assert sub.channels.count() == 0  # server-side assignment only
        assert sub.amount_paid == Decimal("0.00")  # server-controlled default

    def test_patch_cannot_change_sensitive_fields(self, auth_client):
        """PATCH during pending_payment must silently ignore read-only keys."""
        url = reverse("subscriptions:subscriptions-detail", args=[self.sub.id])
        payload = {
            "billing_cycle": "yearly",
            "admin_notes": "hijack",
            "channels": [self.channel.id],
            "is_deleted": True,
            "status": "active",
        }
        response = auth_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        self.sub.refresh_from_db()
        assert self.sub.billing_cycle == "monthly"
        assert self.sub.admin_notes == ""
        assert self.sub.channels.count() == 0
        assert self.sub.is_deleted is False
        assert self.sub.status == "pending_payment"

    def test_patch_can_still_fix_telegram_handle(self, auth_client):
        """telegram_handle remains editable (documented typo-fix path)."""
        url = reverse("subscriptions:subscriptions-detail", args=[self.sub.id])
        response = auth_client.patch(url, {"telegram_handle": "tg_fixed"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert self.sub.telegram_handle == "tg_fixed"

    def test_patch_can_submit_first_payment_proof(self, auth_client):
        """First proof submission during pending_payment is allowed (A6)."""
        url = reverse("subscriptions:subscriptions-detail", args=[self.sub.id])
        response = auth_client.patch(url, {"payment_transaction_hash": "0xabc123"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert self.sub.payment_transaction_hash == "0xabc123"

    def test_patch_cannot_change_proof_after_submission(self, auth_client):
        """Write-once: proof differs from stored value once submitted."""
        self.sub.payment_transaction_hash = "0xoriginal"
        self.sub.save()
        url = reverse("subscriptions:subscriptions-detail", args=[self.sub.id])
        response = auth_client.patch(url, {"payment_transaction_hash": "0xforged"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self.sub.refresh_from_db()
        assert self.sub.payment_transaction_hash == "0xoriginal"


# ============================================================================
# A4 + A6 — edit gate: pending_approval editable, value-aware write-once
# ============================================================================

# Valid 1x1 PNG — DRF's ImageField runs real PIL validation on uploads
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="  # noqa: E501
)


@pytest.mark.django_db
class TestSubscriptionEditGate:
    """A4: editable until an admin decision exists (pending_payment +
    pending_approval). A6: plan/proof checks are value-aware."""

    @pytest.fixture(autouse=True)
    def setup(self, db, user):
        self.user = user
        self.plan = TelegramSignalPlan.objects.create(
            name="Pro",
            slug="pro",
            description="Pro",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )
        self.other_plan = TelegramSignalPlan.objects.create(
            name="Basic",
            slug="basic",
            description="Basic",
            price_monthly=9.99,
            price_quarterly=24.99,
            price_yearly=99.99,
        )
        self.sub = TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_user",
            amount_paid=Decimal("49.99"),
            status="pending_payment",
        )

    def _patch(self, auth_client, payload, sub=None, fmt="json"):
        url = reverse("subscriptions:subscriptions-detail", args=[(sub or self.sub).id])
        return auth_client.patch(url, payload, format=fmt)

    # --- A4: status gate ---

    def test_pending_payment_editable(self, auth_client):
        response = self._patch(auth_client, {"telegram_handle": "tg_fixed"})
        assert response.status_code == status.HTTP_200_OK

    def test_pending_approval_still_editable(self, auth_client):
        """A4: admin has not decided yet — typo fixes must still work."""
        self.sub.status = "pending_approval"
        self.sub.save()
        response = self._patch(auth_client, {"telegram_handle": "tg_fixed"})
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert self.sub.telegram_handle == "tg_fixed"

    def test_pending_approval_can_submit_first_proof(self, auth_client):
        """A4: late proof correction while awaiting approval is legitimate."""
        self.sub.status = "pending_approval"
        self.sub.save()
        response = self._patch(auth_client, {"payment_transaction_hash": "0xlate"})
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert self.sub.payment_transaction_hash == "0xlate"

    def test_frozen_after_approval(self, auth_client, admin_user):
        self.sub.status = "pending_approval"
        self.sub.save()
        self.sub.approve(admin_user)
        response = self._patch(auth_client, {"telegram_handle": "tg_late"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no longer be edited" in str(response.data)

    def test_frozen_after_rejection(self, auth_client):
        self.sub.status = "rejected"
        self.sub.save()
        response = self._patch(auth_client, {"telegram_handle": "tg_late"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_frozen_when_active(self, auth_client):
        self.sub.status = "active"
        self.sub.save()
        response = self._patch(auth_client, {"plan": self.other_plan.id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # --- A6: value-aware plan check ---

    def test_plan_identical_pk_is_noop(self, auth_client):
        """Idempotent PATCH with the same plan must not 400."""
        response = self._patch(auth_client, {"plan": self.plan.id})
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert self.sub.plan_id == self.plan.id

    def test_plan_change_rejected(self, auth_client):
        response = self._patch(auth_client, {"plan": self.other_plan.id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self.sub.refresh_from_db()
        assert self.sub.plan_id == self.plan.id

    # --- A6: value-aware proof check ---

    def test_identical_proof_resubmit_is_noop(self, auth_client):
        self.sub.payment_transaction_hash = "0xdone"
        self.sub.save()
        response = self._patch(auth_client, {"payment_transaction_hash": "0xdone"})
        assert response.status_code == status.HTTP_200_OK

    def test_first_screenshot_upload_allowed(self, auth_client):
        upload = SimpleUploadedFile("proof.png", _PNG_1PX, content_type="image/png")
        response = self._patch(auth_client, {"payment_screenshot": upload}, fmt="multipart")
        assert response.status_code == status.HTTP_200_OK
        self.sub.refresh_from_db()
        assert bool(self.sub.payment_screenshot) is True

    def test_screenshot_replacement_rejected(self, auth_client):
        self.sub.payment_screenshot = SimpleUploadedFile(
            "first.png", _PNG_1PX, content_type="image/png"
        )
        self.sub.save()
        upload = SimpleUploadedFile("second.png", _PNG_1PX, content_type="image/png")
        response = self._patch(auth_client, {"payment_screenshot": upload}, fmt="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        self.sub.refresh_from_db()
        assert "first" in self.sub.payment_screenshot.name


# ============================================================================
# c3b_report fix coverage — A5 / A7 / A10 / A14 / A15
# ============================================================================


@pytest.mark.django_db
class TestResolvePlanPkOrSlug:
    """A5: both subscribe endpoints accept pk OR slug (was: 400 for one form)."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from apps.payments.models import SubscriptionPlan

        self.tg_plan = TelegramSignalPlan.objects.create(
            name="Dual Resolve TG",
            slug="dual-tg",
            description="tg",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=159.99,
        )
        self.bot_plan = SubscriptionPlan.objects.create(
            name="Dual Resolve Bot",
            slug="dual-bot",
            price_monthly="9.99",
            price_yearly="99.99",
            max_bots_allowed=5,
            max_webhooks_allowed=10,
            is_active=True,
        )

    def test_telegram_subscribe_resolves_slug(self, auth_client):
        # Historic gap: slug was rejected with 400 "Invalid plan_id"
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(
            url,
            {
                "plan_id": "dual-tg",  # slug, not UUID
                "telegram_handle": "tg_slug_user",
                "payment_transaction_hash": "0xslugtx",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_telegram_subscribe_resolves_pk(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(
            url,
            {
                "plan_id": str(self.tg_plan.id),
                "telegram_handle": "tg_pk_user",
                "payment_transaction_hash": "0xpktx",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_bot_subscribe_resolves_pk(self, api_client):
        from apps.users.models import CustomUser

        api_client.force_authenticate(
            CustomUser.objects.create_user("pk@t.com", "pk@t.com", "pass")
        )
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": str(self.bot_plan.id)}, format="json")
        assert response.status_code == 201

    def test_bot_subscribe_resolves_slug(self, api_client):
        from apps.users.models import CustomUser

        api_client.force_authenticate(
            CustomUser.objects.create_user("slug@t.com", "slug@t.com", "pass")
        )
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": "dual-bot"}, format="json")
        assert response.status_code == 201

    def test_telegram_inactive_plan_rejected(self, auth_client):
        # _resolve_plan filters is_active=True for both lookup forms
        self.tg_plan.is_active = False
        self.tg_plan.save()
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(
            url,
            {
                "plan_id": str(self.tg_plan.id),
                "telegram_handle": "tg_inactive",
                "payment_transaction_hash": "0xinactive",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTelegramSubscribeBillingAndLimits:
    """A7: billing_cycle honoured, duplicate → 409, capacity enforced."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.plan = TelegramSignalPlan.objects.create(
            name="Cycle Plan",
            slug="cycle-plan",
            description="cycles",
            price_monthly=49.99,
            price_quarterly=129.99,
            price_yearly=499.99,
        )

    def _post(self, auth_client, **extra):
        url = reverse("subscriptions:telegram-subscribe")
        data = {
            "plan_id": str(self.plan.id),
            "telegram_handle": "tg_cycle",
            "payment_transaction_hash": "0xtxcycle",
        }
        data.update(extra)
        return auth_client.post(url, data, format="json")

    def test_default_cycle_is_monthly(self, auth_client):
        response = self._post(auth_client)
        assert response.status_code == status.HTTP_201_CREATED
        sub = TelegramSubscription.objects.get(id=response.data["subscription_id"])
        assert sub.billing_cycle == "monthly"
        assert sub.amount_paid == Decimal("49.99")

    def test_quarterly_cycle_charges_quarterly_price(self, auth_client):
        response = self._post(auth_client, billing_cycle="quarterly")
        assert response.status_code == status.HTTP_201_CREATED
        sub = TelegramSubscription.objects.get(id=response.data["subscription_id"])
        assert sub.billing_cycle == "quarterly"
        assert sub.amount_paid == Decimal("129.99")

    def test_yearly_cycle_charges_yearly_price(self, auth_client):
        response = self._post(auth_client, billing_cycle="yearly")
        assert response.status_code == status.HTTP_201_CREATED
        sub = TelegramSubscription.objects.get(id=response.data["subscription_id"])
        assert sub.billing_cycle == "yearly"
        assert sub.amount_paid == Decimal("499.99")

    def test_invalid_cycle_returns_400_envelope(self, auth_client):
        response = self._post(auth_client, billing_cycle="weekly")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = response.data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert "billing_cycle" in err["message"]

    def test_duplicate_returns_409_envelope(self, auth_client):
        first = self._post(auth_client)
        assert first.status_code == status.HTTP_201_CREATED
        second = self._post(auth_client, telegram_handle="tg_cycle_dup")
        assert second.status_code == status.HTTP_409_CONFLICT
        err = second.data["error"]
        assert err["code"] == "CONFLICT"
        assert "already have" in err["message"]
        # metadata rides along in details (A14 shape)
        assert err["details"]["subscription_id"] == first.data["subscription_id"]
        assert err["details"]["status"] == "pending_approval"

    def test_duplicate_after_terminal_status_allowed(self, auth_client, user):
        # expired/cancelled/rejected rows do NOT block a new subscription
        TelegramSubscription.objects.create(
            user=user,
            plan=self.plan,
            telegram_handle="tg_old",
            amount_paid=Decimal("49.99"),
            status="expired",
        )
        response = self._post(auth_client)
        assert response.status_code == status.HTTP_201_CREATED

    def test_capacity_reached_returns_409(self, auth_client, second_user):
        self.plan.max_subscribers = 1
        self.plan.save()
        # another user fills the last seat (capacity is global, not per user)
        TelegramSubscription.objects.create(
            user=second_user,
            plan=self.plan,
            telegram_handle="tg_seat",
            amount_paid=Decimal("49.99"),
            status="pending_approval",
        )
        response = self._post(auth_client)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "CONFLICT"
        assert "maximum subscribers" in response.data["error"]["message"]

    def test_capacity_null_means_unlimited(self, auth_client, second_user):
        # max_subscribers is None (default) → no capacity check at all
        assert self.plan.max_subscribers is None
        TelegramSubscription.objects.create(
            user=second_user,
            plan=self.plan,
            telegram_handle="tg_many1",
            amount_paid=Decimal("49.99"),
            status="pending_approval",
        )
        TelegramSubscription.objects.create(
            user=second_user,
            plan=self.plan,
            telegram_handle="tg_many2",
            amount_paid=Decimal("49.99"),
            status="pending_approval",
        )
        response = self._post(auth_client)
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestSubscribeErrorEnvelope:
    """A14: subscribe endpoints emit the uniform error envelope, not flat bodies."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from apps.payments.models import SubscriptionPlan

        self.tg_plan = TelegramSignalPlan.objects.create(
            name="Envelope TG",
            slug="env-tg",
            description="env",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=159.99,
        )
        self.bot_plan = SubscriptionPlan.objects.create(
            name="Envelope Bot",
            slug="env-bot",
            price_monthly="9.99",
            price_yearly="99.99",
            max_bots_allowed=5,
            max_webhooks_allowed=10,
            is_active=True,
        )

    def test_telegram_missing_fields_envelope(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = response.data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert "required" in err["message"]
        assert "timestamp" in response.data

    def test_telegram_invalid_plan_envelope(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(
            url,
            {
                "plan_id": "00000000-0000-0000-0000-000000000000",
                "telegram_handle": "tg_x",
                "payment_transaction_hash": "0xx",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_telegram_missing_payment_proof_envelope(self, auth_client):
        url = reverse("subscriptions:telegram-subscribe")
        response = auth_client.post(
            url,
            {"plan_id": str(self.tg_plan.id), "telegram_handle": "tg_nopay"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Payment proof" in response.data["error"]["message"]

    def test_bot_missing_plan_envelope(self, api_client):
        from apps.users.models import CustomUser

        api_client.force_authenticate(
            CustomUser.objects.create_user("env1@t.com", "env1@t.com", "pass")
        )
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "plan_id" in response.data["error"]["message"]

    def test_bot_invalid_plan_envelope(self, api_client):
        from apps.users.models import CustomUser

        api_client.force_authenticate(
            CustomUser.objects.create_user("env2@t.com", "env2@t.com", "pass")
        )
        url = reverse("subscriptions:subscribe")
        response = api_client.post(url, {"plan_id": "nope"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_bot_duplicate_409_envelope(self, api_client):
        from apps.users.models import CustomUser

        user = CustomUser.objects.create_user("env3@t.com", "env3@t.com", "pass")
        api_client.force_authenticate(user)
        url = reverse("subscriptions:subscribe")
        first = api_client.post(url, {"plan_id": "env-bot"}, format="json")
        assert first.status_code == 201
        second = api_client.post(url, {"plan_id": "env-bot"}, format="json")
        assert second.status_code == status.HTTP_409_CONFLICT
        err = second.data["error"]
        assert err["code"] == "CONFLICT"
        assert "already have" in err["message"]
        assert err["details"]["subscription_id"] == first.data["subscription_id"]
        assert err["details"]["status"] == "pending_payment"
        assert "timestamp" in second.data


@pytest.mark.django_db
class TestTelegramPlanFeatures:
    """A10: telegram/plans carries the computed ``features`` object."""

    def test_features_key_present_with_limits(self, api_client):
        plan = TelegramSignalPlan.objects.create(
            name="Feature Plan",
            slug="feature-plan",
            description="f",
            price_monthly=29.99,
            price_quarterly=79.99,
            price_yearly=259.99,
            signals_per_day=25,
            exchanges_covered=["binance", "bybit"],
            risk_level="medium",
        )
        url = reverse("subscriptions:telegram-plan-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        payload = next(p for p in response.data["plans"] if p["id"] == str(plan.id))
        features = payload["features"]
        assert features["max_daily_signals"] == 25
        assert features["exchanges_covered"] == ["binance", "bybit"]
        assert features["risk_level"] == "medium"
        assert features["include_premium_signals"] is False

    def test_include_premium_signals_flag(self, api_client):
        plan = TelegramSignalPlan.objects.create(
            name="Premium Signals XL",
            slug="premium-xl",
            description="p",
            price_monthly=99.99,
            price_quarterly=259.99,
            price_yearly=899.99,
        )
        url = reverse("subscriptions:telegram-plan-list")
        response = api_client.get(url)
        payload = next(p for p in response.data["plans"] if p["id"] == str(plan.id))
        assert payload["features"]["include_premium_signals"] is True


@pytest.mark.django_db
class TestPlanCacheInvalidation:
    """A15: plan saves invalidate both cache keys; subscribe does not."""

    def test_telegram_plan_save_drops_both_keys(self, auth_client):
        plan = TelegramSignalPlan.objects.create(
            name="Cache TG",
            slug="cache-tg",
            description="c",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=159.99,
        )
        # populate telegram_plans_v1 via the endpoint
        assert auth_client.get(reverse("subscriptions:telegram-plan-list")).status_code == 200
        from django.core.cache import cache

        assert cache.get("telegram_plans_v1") is not None
        # seed the other keys manually — receiver must drop ALL on any save
        cache.set("subscription_plans_v1", {"stale": True}, 300)
        cache.set("subscription_plans_v2", {"stale": True}, 300)
        plan.price_monthly = 39.99
        plan.save()
        assert cache.get("telegram_plans_v1") is None
        assert cache.get("subscription_plans_v1") is None
        assert cache.get("subscription_plans_v2") is None

    def test_telegram_plans_fresh_after_edit(self, auth_client):
        plan = TelegramSignalPlan.objects.create(
            name="Stale TG",
            slug="stale-tg",
            description="s",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=159.99,
        )
        url = reverse("subscriptions:telegram-plan-list")
        first = auth_client.get(url)
        payload = next(p for p in first.data["plans"] if p["id"] == str(plan.id))
        assert payload["price_monthly"] == "19.99"
        plan.price_monthly = 79.99
        plan.save()
        second = auth_client.get(url)  # must NOT serve the pre-save cache
        payload = next(p for p in second.data["plans"] if p["id"] == str(plan.id))
        assert payload["price_monthly"] == "79.99"

    def test_subscription_plan_save_drops_both_keys(self, auth_client):
        from django.core.cache import cache

        from apps.payments.models import SubscriptionPlan

        plan = SubscriptionPlan.objects.create(
            name="Cache Bot",
            slug="cache-bot",
            price_monthly="9.99",
            price_yearly="99.99",
            max_bots_allowed=5,
            max_webhooks_allowed=10,
            is_active=True,
        )
        # populate subscription_plans_v2 via the endpoint
        assert auth_client.get(reverse("subscriptions:plan-list")).status_code == 200
        assert cache.get("subscription_plans_v2") is not None
        cache.set("telegram_plans_v1", {"stale": True}, 300)
        cache.set("subscription_plans_v1", {"stale": True}, 300)
        plan.price_monthly = "19.99"
        plan.save()
        assert cache.get("subscription_plans_v2") is None
        assert cache.get("subscription_plans_v1") is None
        assert cache.get("telegram_plans_v1") is None

    def test_bot_plans_fresh_after_edit(self, auth_client):
        from apps.payments.models import SubscriptionPlan

        plan = SubscriptionPlan.objects.create(
            name="Stale Bot",
            slug="stale-bot",
            price_monthly="9.99",
            price_yearly="99.99",
            max_bots_allowed=5,
            max_webhooks_allowed=10,
            is_active=True,
        )
        url = reverse("subscriptions:plan-list")
        first = auth_client.get(url)
        # SubscriptionPlanSerializer.id is IntegerField fed a UUID pk →
        # the payload carries int(uuid); compare in the same form
        payload = next(p for p in first.data["plans"] if p["id"] == int(plan.id))
        assert payload["price_monthly"] == "9.99"
        plan.price_monthly = "49.99"
        plan.save()
        second = auth_client.get(url)
        payload = next(p for p in second.data["plans"] if p["id"] == int(plan.id))
        assert payload["price_monthly"] == "49.99"

    def test_subscribe_does_not_clear_telegram_cache(self, auth_client):
        # subscribe-time cache.delete("telegram_plans_v1") removed by A15
        from django.core.cache import cache

        plan = TelegramSignalPlan.objects.create(
            name="NoWipe TG",
            slug="nowipe-tg",
            description="n",
            price_monthly=19.99,
            price_quarterly=49.99,
            price_yearly=159.99,
        )
        auth_client.get(reverse("subscriptions:telegram-plan-list"))
        assert cache.get("telegram_plans_v1") is not None
        response = auth_client.post(
            reverse("subscriptions:telegram-subscribe"),
            {
                "plan_id": str(plan.id),
                "telegram_handle": "tg_nowipe",
                "payment_transaction_hash": "0xnowipe",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert cache.get("telegram_plans_v1") is not None
