"""
URL patterns for payment processing
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views as payment_views

router = DefaultRouter()
router.register(r'subscription-plans', payment_views.SubscriptionPlanViewSet)
router.register(r'quantum-deposits', payment_views.QuantumDepositViewSet)
router.register(r'withdrawals', payment_views.WithdrawalRequestViewSet)
router.register(r'transactions', payment_views.PaymentTransactionViewSet)

app_name = 'payments'

urlpatterns = [
    # Payment endpoints
    path('', include(router.urls)),

    # Blockchain addresses
    path('blockchain-addresses/', payment_views.BlockchainAddressListView.as_view(), name='blockchain_address_list'),

    # Admin deposit management
    path('admin/deposits/<uuid:deposit_id>/approve/', payment_views.ApproveDepositView.as_view(), name='approve_deposit'),
    path('admin/deposits/<uuid:deposit_id>/reject/', payment_views.RejectDepositView.as_view(), name='reject_deposit'),

    # User deposit management
    path('quantum-ai/<uuid:bot_id>/deposit/', payment_views.CreateDepositView.as_view(), name='create_deposit'),
]