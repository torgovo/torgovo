"""
URL patterns for trading bot endpoints
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bots import indicators_views as indicator_webhooks
from apps.bots import views

# DRF Router for bot viewsets
router = DefaultRouter()
router.register(r"signal-bots", views.SignalBotViewSet, basename="signalbot")
router.register(r"grid-bots", views.GridBotViewSet, basename="gridbot")
router.register(r"martingale-bots", views.MartingaleBotViewSet, basename="martingalebot")
router.register(r"quantum-funds", views.QuantumAIFundViewSet, basename="quantumfund")
router.register(
    r"quantum-investments", views.InvestorPortfolioViewSet, basename="quantuminvestment"
)
router.register(r"pair-configs", views.PairConfigViewSet, basename="pairconfig")
router.register(r"orders", views.OrderViewSet, basename="order")
router.register(r"indicators", views.IndicatorViewSet, basename="indicator")

app_name = "bots"

urlpatterns = [
    # TradingView indicator webhook endpoints (POST with X-Webhook-Token)
    path("indicators/ema/", indicator_webhooks.EMAIndicatorView.as_view(), name="ema-webhook"),
    path("indicators/rsi/", indicator_webhooks.RSIIndicatorView.as_view(), name="rsi-webhook"),
    path("indicators/bb/", indicator_webhooks.BollingerBandsView.as_view(), name="bb-webhook"),
    # DRF Viewset routes (generic — keep after specific paths)
    path("", include(router.urls)),
    # Bot control actions
    path(
        "grid/<str:bot_id>/start/",
        views.GridBotViewSet.as_view({"post": "start"}),
        name="grid-bot-start",
    ),
    path(
        "grid/<str:bot_id>/stop/",
        views.GridBotViewSet.as_view({"post": "stop"}),
        name="grid-bot-stop",
    ),
    path(
        "martingale/<str:bot_id>/start/",
        views.MartingaleBotViewSet.as_view({"post": "start"}),
        name="martingale-bot-start",
    ),
    path(
        "martingale/<str:bot_id>/stop/",
        views.MartingaleBotViewSet.as_view({"post": "stop"}),
        name="martingale-bot-stop",
    ),
]
