"""
URL patterns for user management
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

app_name = 'users'

urlpatterns = [
    # User endpoints
    path('', include(router.urls)),

    # Admin-only endpoints
    path('admin/', views.UserListView.as_view(), name='admin_user_list'),
    path('admin/<int:pk>/', views.UserDetailView.as_view(), name='admin_user_detail'),
    path('admin/dashboard/stats/', views.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('admin/bots/overview/', views.admin_bots_overview, name='admin_bots_overview'),
    path('admin/blockchain-addresses/', views.admin_create_blockchain_address, name='admin_create_blockchain_address'),
    path('admin/trade-logs/', views.admin_trade_logs, name='admin_trade_logs'),
    path('admin/users/<int:pk>/restrict/', views.admin_restrict_user, name='admin_restrict_user'),
    path('admin/emails/send/', views.admin_send_email, name='admin_send_email'),
    path('admin/withdrawals/process/', views.admin_process_withdrawals, name='admin_process_withdrawals'),
]