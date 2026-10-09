"""
URL patterns for admin analytics endpoints.
"""

from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("financial/", views.financial_analytics, name="financial"),
    path("users/", views.user_analytics, name="users"),
    path("trading/", views.trading_analytics, name="trading"),
    path("exchanges/", views.exchange_analytics, name="exchanges"),
]
