"""
URL patterns for Telegram signals subscriptions
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views as subscription_views

router = DefaultRouter()
router.register(r'plans', subscription_views.TelegramSignalPlanViewSet)
router.register(r'subscriptions', subscription_views.TelegramSubscriptionViewSet)
router.register(r'channels', subscription_views.TelegramChannelViewSet)
router.register(r'signals', subscription_views.TradingSignalViewSet)
router.register(r'signal-results', subscription_views.SignalResultViewSet)

app_name = 'subscriptions'

urlpatterns = [
    # Subscription endpoints
    path('', include(router.urls)),

    # Public endpoints
    path('public/plans/', subscription_views.PublicPlanListView.as_view(), name='public_plans'),
    path('subscribe/', subscription_views.CreateSubscriptionView.as_view(), name='create_subscription'),

    # User subscription management
    path('my-subscription/', subscription_views.MySubscriptionView.as_view(), name='my_subscription'),
    path('extend-subscription/', subscription_views.ExtendSubscriptionView.as_view(), name='extend_subscription'),
    path('cancel-subscription/', subscription_views.CancelSubscriptionView.as_view(), name='cancel_subscription'),

    # Admin channel management
    path('admin/channels/', subscription_views.AdminChannelListView.as_view(), name='admin_channel_list'),
    path('admin/channels/create/', subscription_views.AdminCreateChannelView.as_view(), name='admin_create_channel'),

    # Signal statistics
    path('statistics/', subscription_views.SignalStatisticsView.as_view(), name='signal_statistics'),
]