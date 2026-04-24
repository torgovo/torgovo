"""
URL patterns for trading bot endpoints
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.bots import views

# DRF Router for bot viewsets
router = DefaultRouter()
router.register(r'signal-bots', views.SignalBotViewSet, basename='signalbot')
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

    # Old indicator endpoints for manual admin bot
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
    path('indicators/ema/', views.BinanceEMAView.as_view(), name='binance-ema-webhook'),
    path('indicators/rsi/', views.BinanceRSIView.as_view(), name='binance-rsi-webhook'),
    path('indicators/bb/', views.BinanceBBView.as_view(), name='binance-bb-webhook'),

    # Bot control actions
    path('grid/<str:bot_id>/start/', views.GridBotViewSet.as_view({'post': 'start'}), name='grid-bot-start'),
    path('grid/<str:bot_id>/stop/', views.GridBotViewSet.as_view({'post': 'stop'}), name='grid-bot-stop'),
    path('martingale/<str:bot_id>/start/', views.MartingaleBotViewSet.as_view({'post': 'start'}), name='martingale-bot-start'),
    path('martingale/<str:bot_id>/stop/', views.MartingaleBotViewSet.as_view({'post': 'stop'}), name='martingale-bot-stop'),
]