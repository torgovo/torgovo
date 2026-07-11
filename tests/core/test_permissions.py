from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from rest_framework import permissions

from core.permissions import (
    IsOwnerOrReadOnly,
    IsOwnerOrAdmin,
    IsAdminOrReadOnly,
    IsAdminUser,
    IsBotOwner,
    HasValidSubscription,
    CanCreateBots,
    HasExchangeCredentials,
    IsQuantumAIDepositOwner,
    CanApproveDeposits,
    IsWebhookOwner,
)


class TestIsOwnerOrReadOnly:
    @pytest.fixture
    def permission(self):
        return IsOwnerOrReadOnly()

    def test_safe_methods_allowed(self, permission):
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = RequestFactory().generic(method, "/")
            obj = MagicMock()
            assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_write(self, permission):
        user = MagicMock()
        request = RequestFactory().put("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_cannot_write(self, permission):
        request = RequestFactory().post("/")
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
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_superuser_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = True
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_non_admin_cannot_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = MagicMock()
        assert permission.has_object_permission(request, None, obj) is False

    def test_object_without_user_attribute(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
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
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_unauthenticated_user_cannot_read(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_can_write(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = True
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_staff_can_write(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = False
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_cannot_write(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().post("/")
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
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_superuser_allowed(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = True
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_denied(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsBotOwner:
    @pytest.fixture
    def permission(self):
        return IsBotOwner()

    def test_safe_methods_allowed(self, permission):
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = RequestFactory().generic(method, "/")
            obj = MagicMock()
            assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_write(self, permission):
        user = MagicMock()
        request = RequestFactory().post("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_cannot_write(self, permission):
        request = RequestFactory().put("/")
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
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_bypasses_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = True
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_with_active_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        profile = MagicMock()
        profile.has_active_subscription.return_value = True
        user.profile = profile
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_without_profile(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        del user.profile
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_user_without_active_subscription(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        profile = MagicMock()
        profile.has_active_subscription.return_value = False
        user.profile = profile
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestCanCreateBots:
    @pytest.fixture
    def permission(self):
        return CanCreateBots()

    def test_non_post_methods_allowed(self, permission):
        for method in ["GET", "PUT", "PATCH", "DELETE", "HEAD"]:
            request = RequestFactory().generic(method, "/")
            assert permission.has_permission(request, None) is True

    def test_unauthenticated_user_cannot_create(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_admin_can_create(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = True
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_with_capacity(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        profile = MagicMock()
        profile.can_create_more_bots.return_value = True
        user.profile = profile
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_user_without_capacity(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        profile = MagicMock()
        profile.can_create_more_bots.return_value = False
        user.profile = profile
        request = RequestFactory().post("/")
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
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_safe_methods_allowed_for_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().get("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_post_without_exchange_name(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().post("/", data={})
        request.user = user
        assert permission.has_permission(request, None) is True

    @patch("core.permissions.ExchangeCredentials.objects.filter")
    def test_post_with_valid_credentials(self, mock_filter, permission):
        mock_filter.return_value.exists.return_value = True
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().post("/", data={"exchange_name": "binance"})
        request.user = user
        assert permission.has_permission(request, None) is True

    @patch("core.permissions.ExchangeCredentials.objects.filter")
    def test_post_without_credentials(self, mock_filter, permission):
        mock_filter.return_value.exists.return_value = False
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().post("/", data={"exchange_name": "unknown"})
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsQuantumAIDepositOwner:
    @pytest.fixture
    def permission(self):
        return IsQuantumAIDepositOwner()

    def test_admin_can_access(self, permission):
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = True
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        assert permission.has_object_permission(request, None, obj) is True

    def test_owner_can_access(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
        request.user = user
        obj = MagicMock()
        obj.user = user
        assert permission.has_object_permission(request, None, obj) is True

    def test_non_owner_non_admin_denied(self, permission):
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().get("/")
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
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_staff_can_approve(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = False
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_superuser_can_approve(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = True
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_regular_user_denied(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        request = RequestFactory().post("/")
        request.user = user
        assert permission.has_permission(request, None) is False


class TestIsWebhookOwner:
    @pytest.fixture
    def permission(self):
        return IsWebhookOwner()

    def test_post_allows_anyone(self, permission):
        request = RequestFactory().post("/webhooks/")
        assert permission.has_permission(request, None) is True

    def test_get_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = RequestFactory().get("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_get_allows_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().get("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is True

    def test_put_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = False
        request = RequestFactory().put("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is False

    def test_delete_requires_authenticated(self, permission):
        user = MagicMock()
        user.is_authenticated = True
        request = RequestFactory().delete("/webhooks/")
        request.user = user
        assert permission.has_permission(request, None) is True
