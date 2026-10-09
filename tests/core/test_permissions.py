from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory

from core.permissions import (
    CanApproveDeposits,
    CanCreateBots,
    HasExchangeCredentials,
    HasValidSubscription,
    IsAdminOrReadOnly,
    IsAdminUser,
    IsBotOwner,
    IsInvestorDepositOwner,
    IsOwnerOrAdmin,
    IsOwnerOrReadOnly,
    IsWebhookOwner,
)


class TestIsOwnerOrReadOnly:
    @pytest.fixture
    def permission(self):
        return IsOwnerOrReadOnly()

    def test_safe_methods_allowed(self, permission):
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = APIRequestFactory().generic(method, "/")
            obj = MagicMock()
            assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_write(self, permission):
        user = MagicMock()
        request = APIRequestFactory().put("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_cannot_write(self, permission):
        request = APIRequestFactory().post("/")
        request.user = MagicMock()
        obj = MagicMock()
        obj.user = MagicMock()
        assert permission.has_object_permission(request, None, obj) is False


class TestIsOwnerOrAdmin:
    @pytest.fixture
    def permission(self):
        return IsOwnerOrAdmin()

    def test_admin_can_access(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_superuser_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = True
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_non_admin_cannot_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = MagicMock()
        assert permission.has_object_permission(request, None, obj) is False

    def test_object_without_user_attribute(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock(spec=[])  # No user attribute
        assert permission.has_object_permission(request, None, obj) is False


class TestIsAdminOrReadOnly:
    @pytest.fixture
    def permission(self):
        return IsAdminOrReadOnly()

    def test_authenticated_user_can_read(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_unauthenticated_user_cannot_read(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_can_write(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = True
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_staff_can_write(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_cannot_write(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsAdminUser:
    @pytest.fixture
    def permission(self):
        return IsAdminUser()

    def test_staff_allowed(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_superuser_allowed(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = True
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_denied(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsBotOwner:
    @pytest.fixture
    def permission(self):
        return IsBotOwner()

    def test_safe_methods_allowed(self, permission):
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = APIRequestFactory().generic(method, "/")
            obj = MagicMock()
            assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_write(self, permission):
        user = MagicMock()
        request = APIRequestFactory().post("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_cannot_write(self, permission):
        request = APIRequestFactory().put("/")
        request.user = MagicMock()
        obj = MagicMock()
        obj.user = MagicMock()
        assert permission.has_object_permission(request, None, obj) is False


class TestHasValidSubscription:
    @pytest.fixture
    def permission(self):
        return HasValidSubscription()

    def test_unauthenticated_user_denied(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_bypasses_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = True
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_with_active_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.has_active_subscription.return_value = True
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_without_active_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.has_active_subscription.return_value = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestCanCreateBots:
    @pytest.fixture
    def permission(self):
        return CanCreateBots()

    def test_non_post_methods_allowed(self, permission):
        for method in ["GET", "PUT", "PATCH", "DELETE", "HEAD"]:
            request = APIRequestFactory().generic(method, "/")
            assert permission.has_permission(request, None) is True

    def test_unauthenticated_user_cannot_create(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_can_create(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = True
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_with_capacity(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.can_create_more_bots.return_value = True
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_without_capacity(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.can_create_more_bots.return_value = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False


@pytest.mark.django_db
class TestHasExchangeCredentials:
    @pytest.fixture
    def permission(self):
        return HasExchangeCredentials()

    def test_unauthenticated_user_denied(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_safe_methods_allowed_for_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = APIRequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_post_without_exchange_name(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = MagicMock()
        request.method = "POST"
        request.user = user
        request.data = {}
        assert permission.has_permission(request, None) is True

    @patch("apps.exchanges.models.ExchangeCredentials.objects.filter")
    def test_post_with_valid_credentials(self, mock_filter, permission):
        mock_filter.return_value.exists.return_value = True
        user = MagicMock()
        user.is_authenticated = True
        request = MagicMock()
        request.method = "POST"
        request.user = user
        request.data = {"exchange_name": "binance"}
        assert permission.has_permission(request, None) is True

    @patch("apps.exchanges.models.ExchangeCredentials.objects.filter")
    def test_post_without_credentials(self, mock_filter, permission):
        mock_filter.return_value.exists.return_value = False
        user = MagicMock()
        user.is_authenticated = True
        request = MagicMock()
        request.method = "POST"
        request.user = user
        request.data = {"exchange_name": "unknown"}
        assert permission.has_permission(request, None) is False


class TestIsInvestorDepositOwner:
    @pytest.fixture
    def permission(self):
        return IsInvestorDepositOwner()

    def test_admin_can_access(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = True
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_non_admin_denied(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = MagicMock()
        assert permission.has_object_permission(request, None, obj) is False


class TestCanApproveDeposits:
    @pytest.fixture
    def permission(self):
        return CanApproveDeposits()

    def test_unauthenticated_denied(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_staff_can_approve(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_superuser_can_approve(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = True
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_denied(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        request = APIRequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsWebhookOwner:
    @pytest.fixture
    def permission(self):
        return IsWebhookOwner()

    def test_post_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().post("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_post_allows_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = APIRequestFactory().post("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_get_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().get("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_get_allows_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = APIRequestFactory().get("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_put_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = APIRequestFactory().put("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_delete_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = APIRequestFactory().delete("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is True
