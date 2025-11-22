"""
URL patterns for trading bot endpoints
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import views
from . import views as bot_views
from . import indicators_views

router = DefaultRouter()
router.register(r'webhook-alerts', bot_views.WebhookAlertViewSet)
router.register(r'grid-bots', bot_views.GridBotViewSet)
router.register(r'martingale-bots', bot_views.MartingaleBotViewSet)
router.register(r'quantum-ai-bots', bot_views.QuantumAIBotViewSet)
router.register(r'orders', bot_views.OrderViewSet)

app_name = 'bots'

urlpatterns = [
    # Main API endpoints
    path('', include(router.urls)),

    # Bot control endpoints
    path('grid/<uuid:bot_id>/start/', bot_views.start_grid_bot, name='start_grid_bot'),
    path('grid/<uuid:bot_id>/stop/', bot_views.stop_grid_bot, name='stop_grid_bot'),
    path('martingale/<uuid:bot_id>/start/', bot_views.start_martingale_bot, name='start_martingale_bot'),
    path('martingale/<uuid:bot_id>/stop/', bot_views.stop_martingale_bot, name='stop_martingale_bot'),
    path('quantum-ai/<uuid:bot_id>/start/', bot_views.start_quantum_ai_bot, name='start_quantum_ai_bot'),
    path('quantum-ai/<uuid:bot_id>/stop/', bot_views.stop_quantum_ai_bot, name='stop_quantum_ai_bot'),

    # Technical indicators endpoints
    path('indicators/', include(indicators_urls)),

    # Bot statistics and monitoring
    path('stats/overview/', bot_views.bots_overview, name='bots_overview'),
    path('stats/performance/<uuid:bot_id>/', bot_views.bot_performance, name='bot_performance'),
]

# Technical indicators URLs
indicators_urls = [
    path('ema/', indicators_views.EMAIndicatorView.as_view(), name='ema_webhook'),
    path('rsi/', indicators_views.RSIIndicatorView.as_view(), name='rsi_webhook'),
    path('bollinger-bands/', indicators_views.BollingerBandsView.as_view(), name='bb_webhook'),
]