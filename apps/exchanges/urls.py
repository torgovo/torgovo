"""Legacy compatibility URLs for exchange endpoints.

The canonical exchange surface now lives under the trading app. This module
preserves the public legacy namespace while delegating implementation to the
single source of truth in apps.trading.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.trading.views import (
    ExchangeCredentialsViewSet,
    ExchangeStatusViewSet,
    TradingPairViewSet,
    get_exchange_rates,
    get_exchange_symbols,
    list_exchanges,
)

from . import views as exchange_views

router = DefaultRouter()
router.register(r"credentials", ExchangeCredentialsViewSet, basename="credentials")
router.register(r"supported-pairs", TradingPairViewSet, basename="supported-pairs")
router.register(r"status", ExchangeStatusViewSet, basename="status")
router.register(
    r"blockchain-addresses",
    exchange_views.BlockchainAddressViewSet,
    basename="blockchain-addresses",
)

app_name = "exchanges"

urlpatterns = [
    # Legacy compatibility endpoints; canonical implementations live in apps.trading.
    path("", include(router.urls)),
    path("list/", list_exchanges, name="list_exchanges"),
    path(
        "<str:exchange_name>/symbols/",
        get_exchange_symbols,
        name="get_exchange_symbols",
    ),
    path("rates/", get_exchange_rates, name="get_exchange_rates"),
]
