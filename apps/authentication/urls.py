"""
URL patterns for authentication app
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'authentication'

urlpatterns = [
    # Authentication endpoints
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('logout/', views.UserLogoutView.as_view(), name='logout'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('profile/update/', views.UpdateProfileView.as_view(), name='profile-update'),
    path('user/', views.UserDetailView.as_view(), name='user-detail'),

    # Email verification
    path('verify-email/', views.EmailVerificationView.as_view(), name='verify-email-request'),
    path('verify-email/<str:token>/', views.verify_email, name='verify-email'),

    # Phone verification
    path('verify-phone/', views.PhoneVerificationRequestView.as_view(), name='verify-phone-request'),
    path('verify-phone/confirm/', views.PhoneVerificationConfirmView.as_view(), name='verify-phone-confirm'),

    # Password reset
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # Change password
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),

    # Social authentication
    path('google/', views.GoogleAuthView.as_view(), name='google-auth'),

    # Token refresh
    path('refresh-token/', views.RefreshTokenView.as_view(), name='refresh-token'),
]