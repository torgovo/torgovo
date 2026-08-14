"""
URL patterns for exchange integration
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views as exchange_views

router = DefaultRouter()
router.register(r"credentials", exchange_views.ExchangeCredentialsViewSet, basename="credentials")
router.register(r"supported-pairs", exchange_views.TradingPairViewSet, basename="supported-pairs")
router.register(r"status", exchange_views.ExchangeStatusViewSet, basename="status")
router.register(
    r"blockchain-addresses",
    exchange_views.BlockchainAddressViewSet,
    basename="blockchain-addresses",
)

app_name = "exchanges"

urlpatterns = [
    # Exchange endpoints
    path("", include(router.urls)),
    # Exchange-specific endpoints
    path("list/", exchange_views.list_exchanges, name="list_exchanges"),
    path(
        "<str:exchange_name>/symbols/",
        exchange_views.get_exchange_symbols,
        name="get_exchange_symbols",
    ),
    path("rates/", exchange_views.get_exchange_rates, name="get_exchange_rates"),
]
