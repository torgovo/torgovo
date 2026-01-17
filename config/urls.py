"""
Main URL configuration for Torgovo Trading Platform
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

# API Router for main endpoints
router = DefaultRouter()

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),

    # API Root
    path('api/', include(router.urls)),

    # App-specific URLs
    path('api/bots/', include('apps.bots.urls', namespace='bots')),
    path('api/payments/', include('apps.payments.urls', namespace='payments')),
    path('api/auth/', include('apps.authentication.urls', namespace='auth')),
    path('api/users/', include('apps.users.urls', namespace='users')),
    path('api/exchanges/', include('apps.exchanges.urls', namespace='exchanges')),
    path('api/subscriptions/', include('apps.subscriptions.urls', namespace='subscriptions')),

    # Custom Bot Webhook (global URL, secret in JSON payload)
    path('api/webhooks/custombot/', include('apps.webhooks.urls', namespace='custombot_webhooks')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Debug toolbar (optional)
if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns = [
                      path('__debug__/', include(debug_toolbar.urls)),
                  ] + urlpatterns

# Django Silk profiler (optional)
if 'silk' in settings.INSTALLED_APPS:
    urlpatterns = [
                      path('silk/', include('silk.urls', namespace='silk')),
                  ] + urlpatterns