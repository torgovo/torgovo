"""
URL configuration for Torgovo Crypto Trading Platform
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication URLs
    path('api/auth/', include('apps.authentication.urls')),

    # Main API endpoints
    path('api/', include('apps.webhooks.urls')),
    path('api/', include('apps.bots.urls')),
    path('api/', include('apps.exchanges.urls')),
    path('api/', include('apps.payments.urls')),
    path('api/', include('apps.subscriptions.urls')),
    path('api/', include('apps.users.urls')),

    
    # Admin endpoints
    path('api/admin/', include('apps.users.urls')),

    # Health check
    path('health/', TemplateView.as_view(template_name='health.html'), name='health'),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom admin site configuration
admin.site.site_header = 'Torgovo Admin'
admin.site.site_title = 'Torgovo Trading Platform'
admin.site.index_title = 'Welcome to Torgovo Trading Platform Administration'