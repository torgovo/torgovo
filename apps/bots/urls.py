"""
URL patterns for trading bot endpoints
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.payments import views

# DRF Router for bot viewsets
router = DefaultRouter()
router.register(r'custom-bots', views.CustomBotViewSet, basename='custombot')
router.register(r'grid-bots', views.GridBotViewSet, basename='gridbot')
router.register(r'martingale-bots', views.MartingaleBotViewSet, basename='martingalebot')
router.register(r'quantum-funds', views.QuantumAIFundViewSet, basename='quantumfund')
router.register(r'quantum-investments', views.QuantumAIInvestmentViewSet, basename='quantuminvestment')
router.register(r'pair-configs', views.PairConfigViewSet, basename='pairconfig')
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'indicators', views.IndicatorViewSet, basename='indicator')
router.register(r'telegram-plans', views.TelegramSignalPlanViewSet, basename='telegramplan')
router.register(r'telegram-subscriptions', views.TelegramSignalSubscriptionViewSet, basename='telegramsub')

app_name = 'bots'

urlpatterns = [
    # DRF Viewset routes
    path('', include(router.urls)),

    # ========== QUANTUM AI BOT ENDPOINTS (Admin Strategy) ==========
    # These receive TradingView EMA/RSI/BB data for the ADMIN's Quantum AI strategy
    path('indicators/binance/<str:username>/<str:pair>/',
         views.IndicatorView.as_view(),
         name='binance-indicator'),
    path('indicators/bybit/<str:username>/<str:pair>/',
         views.BybitIndicatorView.as_view(),
         name='bybit-indicator'),
    path('indicators/close/<str:username>/<str:pair>/',
         views.CustomOrderClosingView.as_view(),
         name='close-order'),
    path('indicators/open/<str:username>/<str:pair>/<str:side>/',
         views.CustomOrderOpeningView.as_view(),
         name='open-order'),

    # TradingView webhooks for Quantum AI indicators (admin bot updates)
    path('indicators/ema/', views.BinanceEMAView.as_view(), name='binance-ema-webhook'),
    path('indicators/rsi/', views.BinanceRSIView.as_view(), name='binance-rsi-webhook'),
    path('indicators/bb/', views.BinanceBBView.as_view(), name='binance-bb-webhook'),

    # ========== EXISTING BOT CONTROL ENDPOINTS ==========
    # Grid Bot control actions
    path('grid/<str:bot_id>/start/',
         views.GridBotViewSet.as_view({'post': 'start'}),
         name='grid-bot-start'),
    path('grid/<str:bot_id>/stop/',
         views.GridBotViewSet.as_view({'post': 'stop'}),
         name='grid-bot-stop'),

    # Martingale Bot control actions
    path('martingale/<str:bot_id>/start/',
         views.MartingaleBotViewSet.as_view({'post': 'start'}),
         name='martingale-bot-start'),
    path('martingale/<str:bot_id>/stop/',
         views.MartingaleBotViewSet.as_view({'post': 'stop'}),
         name='martingale-bot-stop'),

    # ========== WEBHOOK ALERT ENDPOINTS ==========
    # NEW: CustomBot webhook for consumer strategies (TradingView alerts)
    # Format: POST /api/bots/webhook/{bot_id}/{secret_key}/
    path('webhook/<str:bot_id>/<str:secret_key>/',
         views.WebhookSignalView.as_view(),
         name='webhook_signal'),

    # Keep existing webhook endpoints (if any other services use them)
    path("custombot/", views.CustomBotWebhookView.as_view(), name="custombot_webhook"),
    path("grid/", views.GridBotWebhookView.as_view(), name="grid_webhook"),
    path("martingale/", views.MartingaleBotWebhookView.as_view(), name="martingale_webhook"),
    path("quantumai/", views.QuantumAIWebhookView.as_view(), name="quantum_ai_webhook"),

    # ========== BOT MANAGEMENT ENDPOINTS ==========
    path("start/<str:bot_id>/", views.StartBotView.as_view(), name="start_bot"),
    path("stop/<str:bot_id>/", views.StopBotView.as_view(), name="stop_bot"),
    path("status/<str:bot_id>/", views.BotStatusView.as_view(), name="bot_status"),
]