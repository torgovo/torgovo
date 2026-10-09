"""
Main URL configuration for Torgovo Trading Platform
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users.admin_site import admin_site
from core.health import health_check


def metrics_view(request):
    """Prometheus metrics endpoint (thin wrapper for django_prometheus)."""
    from django_prometheus.exports import ExportToDjangoView

    return ExportToDjangoView(request)


# API Router for main endpoints
router = DefaultRouter()

urlpatterns = [
    # Prometheus metrics
    path("", include("django_prometheus.urls")),
    path("metrics", metrics_view, name="metrics"),
    # Health check (comprehensive — DB, Redis, disk)
    path("health/", health_check, name="health"),
    # Legacy health check
    path("ht/", include("health_check.urls")),
    # Django Admin
    path("admin/", admin_site.urls),
    # API Root
    path("api/", include(router.urls)),
    # App-specific URLs
    path("api/bots/", include("apps.bots.urls", namespace="bots")),
    path("api/payments/", include("apps.payments.urls", namespace="payments")),
    path("api/auth/", include("apps.authentication.urls", namespace="auth")),
    path("api/users/", include("apps.users.urls", namespace="users")),
    path(
        "api/trading/", include("apps.trading.urls", namespace="trading")
    ),  # New unified trading API
    path(
        "api/exchanges/",
        include("apps.exchanges.urls", namespace="exchanges"),
    ),  # Deprecated compatibility alias; canonical routes live under api/trading/
    path("api/subscriptions/", include("apps.subscriptions.urls", namespace="subscriptions")),
    path("api/investments/", include("apps.investments.urls", namespace="investments")),
    path("api/referrals/", include("apps.referrals.urls", namespace="referrals")),
    path("api/analytics/", include("apps.analytics.urls", namespace="analytics")),
    # Custom Bot Webhook (global URL, secret in JSON payload)
    path("api/webhooks/custombot/", include("apps.webhooks.urls", namespace="custombot_webhooks")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Debug toolbar (optional)
if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

# Django Silk profiler (optional)
if "silk" in settings.INSTALLED_APPS:
    urlpatterns = [
        path("silk/", include("silk.urls", namespace="silk")),
    ] + urlpatterns
