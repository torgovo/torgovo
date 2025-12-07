"""
Referrals App URL Configuration for Torgovo Platform
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'referrals'

router = DefaultRouter()
# Add your referral viewsets here when you create them
# router.register(r'referrals', views.ReferralViewSet, basename='referral')

urlpatterns = [
    path('api/', include(router.urls)),
    # Add referral endpoints here
    # path('api/referrals/links/', views.ReferralLinkView.as_view(), name='referral-links'),
]