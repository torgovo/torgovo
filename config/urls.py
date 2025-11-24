from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API endpoints - temporarily disabled incomplete apps
    # path('api/auth/', include('apps.authentication.urls')),
    # path('api/webhooks/', include('apps.webhooks.urls')),
    # path('api/bots/', include('apps.bots.urls')),
    # path('api/exchanges/', include('apps.webhooks.urls')),
    # path('api/payments/', include('apps.payments.urls')),
    # path('api/subscriptions/', include('apps.subscriptions.urls')),
    # path('api/users/', include('apps.users.urls')),
    # path('api/investments/', include('apps.investments.urls')),
    # path('api/referrals/', include('apps.referrals.urls')),
    
    # Allauth - temporarily disabled
    # path('accounts/', include('allauth.urls')),
    
    # Health check
    path('health/', lambda request: HttpResponse('OK')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
