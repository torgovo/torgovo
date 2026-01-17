"""
URL patterns for payment processing and bot subscriptions
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views as payment_views

# DRF Router for payment viewsets
router = DefaultRouter()
router.register(r'subscription-plans', payment_views.SubscriptionPlanViewSet, basename='subscriptionplan')
router.register(r'quantum-deposits', payment_views.QuantumDepositViewSet, basename='quantumdeposit')
router.register(r'withdrawals', payment_views.WithdrawalRequestViewSet, basename='withdrawal')
router.register(r'transactions', payment_views.PaymentTransactionViewSet, basename='paymenttransaction')

app_name = 'payments'

urlpatterns = [
    # DRF Viewset routes
    path('', include(router.urls)),
    
    # Blockchain addresses
    path('blockchain-addresses/', payment_views.BlockchainAddressListView.as_view(), name='blockchain_address_list'),
    
    # Admin deposit management (Quantum AI)
    path('admin/deposits/<uuid:deposit_id>/approve/', payment_views.ApproveDepositView.as_view(), name='approve_deposit'),
    path('admin/deposits/<uuid:deposit_id>/reject/', payment_views.RejectDepositView.as_view(), name='reject_deposit'),
    
    # Bot subscription management (NEW - moved from bots app)
    path('subscriptions/bot/', payment_views.BotSubscriptionViewSet.as_view({'get': 'list'}), name='bot-subscription-list'),
    path('subscriptions/bot/create/', payment_views.CreateBotSubscriptionView.as_view(), name='bot-subscription-create'),
    path('subscriptions/bot/<str:subscription_id>/approve/', 
         payment_views.AdminApproveSubscriptionView.as_view(), 
         name='admin-approve-subscription'),
    path('subscriptions/bot/<str:subscription_id>/reject/', 
         payment_views.AdminRejectSubscriptionView.as_view(), 
         name='admin-reject-subscription'),
    
    # User deposit management (Quantum AI)
    path('quantum-ai/<uuid:bot_id>/deposit/', payment_views.CreateDepositView.as_view(), name='create_deposit'),
]