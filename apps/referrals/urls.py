"""
Referrals App URL Configuration for Torgovo Platform
"""
from django.urls import path
from . import views

app_name = 'referrals'

urlpatterns = [
    # User referral endpoints
    path('my-stats/', views.MyReferralStatsView.as_view(), name='my-referral-stats'),
    path('apply/', views.ApplyReferralCodeView.as_view(), name='apply-referral-code'),
]