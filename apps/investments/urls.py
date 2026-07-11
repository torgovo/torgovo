"""
Investment App URL Configuration for Torgovo Platform
Maps to API endpoints from DOCUMENTATION.md
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'investments'

# API Router for REST endpoints
router = DefaultRouter()
router.register(r'exchanges', views.ExchangeViewSet, basename='exchange')
router.register(r'credentials', views.ExchangeCredentialViewSet, basename='credential')
router.register(r'trading-pairs', views.TradingPairViewSet, basename='trading-pair')
router.register(r'bots/webhook-alerts', views.WebhookAlertBotViewSet, basename='webhook-bot')
router.register(r'bots/grid-bots', views.GridBotViewSet, basename='grid-bot')
router.register(r'bots/martingale-bots', views.MartingaleBotViewSet, basename='martingale-bot')
router.register(r'bots/quantum-ai-bots', views.QuantumAIBotViewSet, basename='quantum-ai-bot')
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'positions', views.PositionViewSet, basename='position')
router.register(r'technical-indicators', views.TechnicalIndicatorViewSet, basename='indicator')
router.register(r'balances', views.UserBalanceViewSet, basename='balance')

# Webhook endpoints (public, but secured with secret)
webhook_patterns = [
    path('tradingview/<uuid:webhook_id>/', views.TradingViewWebhookView.as_view(), name='tradingview-webhook'),
]

# Main URL patterns
urlpatterns = [
    # Exchange management (must come before router to avoid capture by exchange-detail)
    path('exchanges/list/', views.ExchangeListView.as_view(), name='exchange-list-view'),
    path('exchanges/<str:exchange_name>/symbols/', views.ExchangeSymbolsView.as_view(), name='exchange-symbols'),
    
    # API routes (these use the router)
    path('', include(router.urls)),
    
    # Webhook routes
    path('webhooks/', include(webhook_patterns)),
    
    # Technical indicators (manual POST endpoints)
    path('indicators/ema/manual/', views.EMAIndicatorView.as_view(), name='ema-indicator'),
    path('indicators/ema/', views.EMAWebhookView.as_view(), name='ema-webhook'),
    path('indicators/rsi/manual/', views.RSIIndicatorView.as_view(), name='rsi-indicator'),
    path('indicators/rsi/', views.RSIWebhookView.as_view(), name='rsi-webhook'),
    
    # User management
    path('users/my-orders/', views.UserOrdersView.as_view(), name='user-orders'),
    path('users/profile/', views.UserProfileView.as_view(), name='user-profile'),
    
    # Quantum AI blockchain addresses
    path('bots/blockchain-addresses/', views.BlockchainAddressesView.as_view(), name='blockchain-addresses'),
    path('bots/quantum-ai/<uuid:bot_id>/deposit/', views.QuantumAIDepositView.as_view(), name='quantum-deposit'),
    
    # Bot actions
    path('bots/<uuid:bot_id>/start/', views.StartBotView.as_view(), name='bot-start'),
    path('bots/<uuid:bot_id>/stop/', views.StopBotView.as_view(), name='bot-stop'),
    path('bots/<uuid:bot_id>/pause/', views.PauseBotView.as_view(), name='bot-pause'),
]