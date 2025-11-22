"""
URL patterns for webhook endpoints
"""
from django.urls import path
from . import views

app_name = 'webhooks'

urlpatterns = [
    # TradingView webhook endpoint
    path('tradingview/<uuid:webhook_id>/', views.TradingViewWebhookView.as_view(), name='tradingview_webhook'),

    # Technical indicator endpoints
    path('indicators/ema/', views.EMAIndicatorView.as_view(), name='ema_indicator'),
    path('indicators/rsi/', views.RSIIndicatorView.as_view(), name='rsi_indicator'),
]