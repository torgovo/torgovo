"""
URL patterns for webhook endpoints
"""

from django.urls import path

from . import views

app_name = "webhooks"

urlpatterns = [
    # Custom Bot webhook endpoint (global URL, secret in JSON)
    path("", views.SignalBotWebhookView.as_view(), name="signalbot_webhook"),
]
