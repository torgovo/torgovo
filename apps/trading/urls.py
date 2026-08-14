"""
URL patterns for trading app
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"exchanges", views.ExchangeViewSet, basename="exchanges")
router.register(r"credentials", views.ExchangeCredentialsViewSet, basename="credentials")
router.register(r"pairs", views.TradingPairViewSet, basename="pairs")
router.register(r"status", views.ExchangeStatusViewSet, basename="status")
router.register(r"strategy-configs", views.StrategyConfigViewSet, basename="strategy-configs")

app_name = "trading"

urlpatterns = [
    # Function-based views (before viewset routes to avoid capture)
    path("exchanges/list/", views.list_exchanges, name="list_exchanges"),
    # ViewSet routes
    path("", include(router.urls)),
    path(
        "exchanges/<str:exchange_name>/symbols/",
        views.get_exchange_symbols,
        name="get_exchange_symbols",
    ),
    path("rates/", views.get_exchange_rates, name="get_exchange_rates"),
]
