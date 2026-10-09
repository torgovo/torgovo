"""
Investment App URL Configuration for Torgovo Platform
Maps to API endpoints from DOCUMENTATION.md
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "investments"

# API Router for REST endpoints
router = DefaultRouter()
router.register(r"orders", views.OrderViewSet, basename="order")
router.register(r"positions", views.PositionViewSet, basename="position")
router.register(r"technical-indicators", views.TechnicalIndicatorViewSet, basename="indicator")
router.register(r"balances", views.UserBalanceViewSet, basename="balance")

urlpatterns = [
    path("", include(router.urls)),
    # User management
    path("users/my-orders/", views.UserOrdersView.as_view(), name="user-orders"),
    path("users/profile/", views.UserProfileView.as_view(), name="user-profile"),
    # Quantum AI blockchain addresses
    path(
        "bots/blockchain-addresses/",
        views.BlockchainAddressesView.as_view(),
        name="blockchain-addresses",
    ),
    path(
        "bots/quantum-ai/<uuid:bot_id>/deposit/",
        views.InvestorDepositView.as_view(),
        name="quantum-deposit",
    ),
]
