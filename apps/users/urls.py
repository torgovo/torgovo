"""
URL patterns for user management
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import admin_views as admin_api
from . import views as user_views

router = DefaultRouter()
router.register(r'profiles', user_views.UserProfileViewSet)
router.register(r'orders', user_views.UserOrderViewSet)

app_name = 'users'

urlpatterns = [
    # User endpoints
    path('', include(router.urls)),

    # Admin-only endpoints
    path('admin/', admin_api.UserListView.as_view(), name='admin_user_list'),
    path('admin/<uuid:pk>/', admin_api.UserDetailView.as_view(), name='admin_user_detail'),
    path('admin/dashboard/stats/', admin_api.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('admin/bots/overview/', admin_api.admin_bots_overview, name='admin_bots_overview'),
    path('admin/blockchain-addresses/', admin_api.admin_create_blockchain_address, name='admin_create_blockchain_address'),

    # User-specific endpoints
    path('my-orders/', user_views.UserOrderListView.as_view(), name='user_order_list'),
    path('my-stats/', user_views.UserStatsView.as_view(), name='user_stats'),
]