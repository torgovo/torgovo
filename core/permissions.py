"""
Custom permissions for Torgovo Crypto Trading Platform
"""

from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the object.
        return obj.user == request.user


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admin to access it.
    """

    def has_object_permission(self, request, view, obj):
        # Admin can access any object
        if request.user.is_staff or request.user.is_superuser:
            return True

        # Owner can access their own objects
        return hasattr(obj, "user") and obj.user == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to write.
    Read-only access is allowed for authenticated users.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated

        return request.user.is_staff or request.user.is_superuser


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users.
    """

    def has_permission(self, request, view):
        return request.user.is_staff or request.user.is_superuser


class IsBotOwner(permissions.BasePermission):
    """
    Custom permission for trading bot access.
    Only allows users to access their own bots.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return obj.user == request.user


class HasValidSubscription(permissions.BasePermission):
    """
    Custom permission to check if user has active subscription.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Admin users bypass subscription check
        if request.user.is_staff or request.user.is_superuser:
            return True

        return request.user.has_active_subscription()


class CanCreateBots(permissions.BasePermission):
    """
    Custom permission to check if user can create more bots.
    """

    def has_permission(self, request, view):
        if request.method != "POST":
            return True

        if not request.user.is_authenticated:
            return False

        # Admin users have no limits
        if request.user.is_staff or request.user.is_superuser:
            return True

        return request.user.can_create_more_bots()


class HasExchangeCredentials(permissions.BasePermission):
    """
    Custom permission to check if user has valid exchange credentials.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # For GET requests, allow authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True

        # For POST/PUT/DELETE requests, check exchange credentials
        exchange_name = request.data.get("exchange_name")
        if not exchange_name:
            return True  # Will be validated in serializer

        from apps.exchanges.models import ExchangeCredentials

        return ExchangeCredentials.objects.filter(
            user=request.user, exchange_name=exchange_name, is_active=True
        ).exists()


class IsInvestorDepositOwner(permissions.BasePermission):
    """
    Custom permission for Quantum AI deposit access.
    """

    def has_object_permission(self, request, view, obj):
        # Admin can access all deposits
        if request.user.is_staff or request.user.is_superuser:
            return True

        # User can access their own deposits
        return hasattr(obj, "user") and obj.user == request.user


class CanApproveDeposits(permissions.BasePermission):
    """
    Custom permission for deposit approval (admin only).
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )


class IsWebhookOwner(permissions.BasePermission):
    """
    Custom permission for webhook access.
    Requires authentication for all methods.
    Webhook secret validation is handled separately in view logic.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated


# IsInvestorDepositOwner (was IsQuantumAIDepositOwner)
IsQuantumAIDepositOwner = IsInvestorDepositOwner
