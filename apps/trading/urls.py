"""
URL patterns for trading app
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'exchanges', views.ExchangeViewSet, basename='exchanges')
router.register(r'credentials', views.ExchangeCredentialsViewSet, basename='credentials')
router.register(r'pairs', views.TradingPairViewSet, basename='pairs')
router.register(r'status', views.ExchangeStatusViewSet, basename='status')
router.register(r'bots', views.BotConfigurationViewSet, basename='bots')

app_name = 'trading'

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),

    # Function-based views
    path('exchanges/list/', views.list_exchanges, name='list_exchanges'),
    path('exchanges/<str:exchange_name>/symbols/', views.get_exchange_symbols, name='get_exchange_symbols'),
    path('rates/', views.get_exchange_rates, name='get_exchange_rates'),
]
