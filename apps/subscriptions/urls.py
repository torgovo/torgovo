"""
URL patterns for Telegram signals subscriptions
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views as subscription_views

router = DefaultRouter()
router.register(r"plans", subscription_views.TelegramSignalPlanViewSet, basename="plans")
router.register(
    r"subscriptions", subscription_views.TelegramSubscriptionViewSet, basename="subscriptions"
)
router.register(r"channels", subscription_views.TelegramChannelViewSet, basename="channels")
router.register(r"signals", subscription_views.TradingSignalViewSet, basename="signals")
router.register(
    r"signal-results", subscription_views.SignalResultViewSet, basename="signal-results"
)

app_name = "subscriptions"


urlpatterns = [
    path("", include(router.urls)),
    path("public/plans/", subscription_views.PublicPlanListView.as_view(), name="public_plans"),
    path(
        "my-subscription/", subscription_views.MySubscriptionView.as_view(), name="my_subscription"
    ),
    path(
        "admin/channels/",
        subscription_views.AdminChannelListView.as_view(),
        name="admin_channel_list",
    ),
    path(
        "admin/channels/create/",
        subscription_views.AdminCreateChannelView.as_view(),
        name="admin_create_channel",
    ),
    path(
        "telegram/plans/",
        subscription_views.TelegramPlanListView.as_view(),
        name="telegram-plan-list",
    ),
    path(
        "telegram/my-usage/",
        subscription_views.MyTelegramUsageView.as_view(),
        name="telegram-my-usage",
    ),
    path(
        "telegram/subscribe/",
        subscription_views.TelegramSubscribeView.as_view(),
        name="telegram-subscribe",
    ),
    path("bot-plans/", subscription_views.PlanListView.as_view(), name="plan-list"),
    path("bot-subscribe/", subscription_views.SubscribeView.as_view(), name="subscribe"),
    path("bot-my-usage/", subscription_views.MyUsageView.as_view(), name="my-usage"),
]
