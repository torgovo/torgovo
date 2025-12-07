"""
Serializers for authentication app
"""
import uuid
import secrets
from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import (
    UserProfile, EmailVerification,
    PhoneVerification, PasswordResetToken
)
# Import CustomUser from users app (AUTH_USER_MODEL = 'users.CustomUser')
from apps.users.models import CustomUser
from core.utils import generate_secret_key


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone_number'
        )

    def validate_email(self, value):
        """Validate email uniqueness."""
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_username(self, value):
        """Validate username uniqueness."""
        if CustomUser.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_phone_number(self, value):
        """Validate phone number uniqueness."""
        if value and CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def create(self, validated_data):
        """Create user and profile."""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        user = CustomUser.objects.create_user(
            password=password,
            **validated_data
        )

        # Create user profile
        UserProfile.objects.create(user=user)

        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate credentials."""
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                username=email,
                password=password
            )

            if not user:
                raise serializers.ValidationError('Invalid credentials.')

            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')

            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include email and password.')


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    subscription_plan_display = serializers.CharField(source='get_subscription_plan_display', read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            'id', 'user_email', 'user_full_name', 'subscription_plan',
            'subscription_plan_display', 'max_bots_allowed', 'timezone',
            'demo_trading_enabled', 'email_notifications',
            'sms_notifications', 'push_notifications',
            'subscription_start_date', 'subscription_end_date',
            'is_subscription_active', 'referral_code',
            'total_trades_executed', 'total_volume_traded',
            'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'max_bots_allowed', 'subscription_start_date',
            'subscription_end_date', 'is_subscription_active',
            'referral_code', 'total_trades_executed',
            'total_volume_traded', 'created_at', 'updated_at'
        )


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user data."""
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = CustomUser
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name',
            'full_name', 'phone_number', 'is_email_verified',
            'is_phone_verified', 'date_joined', 'last_login',
            'timezone', 'two_factor_enabled', 'profile'
        )
        read_only_fields = (
            'id', 'is_email_verified', 'is_phone_verified',
            'date_joined', 'last_login', 'two_factor_enabled'
        )


class EmailVerificationSerializer(serializers.ModelSerializer):
    """Serializer for email verification."""
    class Meta:
        model = EmailVerification
        fields = ('user', 'token', 'expires_at')
        read_only_fields = ('token', 'expires_at')

    def create(self, validated_data):
        """Create email verification token."""
        user = validated_data['user']
        token = generate_secret_key(64)
        expires_at = timezone.now() + timedelta(hours=24)

        # Invalidate existing tokens
        EmailVerification.objects.filter(user=user, is_verified=False).update(
            is_verified=True
        )

        return EmailVerification.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )


class PhoneVerificationSerializer(serializers.Serializer):
    """Serializer for phone verification."""
    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value):
        """Validate phone number format."""
        import re
        if not re.match(r'^\+?1?\d{9,15}$', value):
            raise serializers.ValidationError("Invalid phone number format.")
        return value

    def create(self, validated_data):
        """Create phone verification code."""
        from apps.authentication.signals import generate_otp_code

        user = self.context['request'].user
        phone_number = validated_data['phone_number']
        code = generate_otp_code()
        expires_at = timezone.now() + timedelta(minutes=10)

        # Invalidate existing codes
        PhoneVerification.objects.filter(
            user=user,
            is_verified=False
        ).update(is_verified=True)

        return PhoneVerification.objects.create(
            user=user,
            code=code,
            phone_number=phone_number,
            expires_at=expires_at
        )


class PhoneVerificationConfirmSerializer(serializers.Serializer):
    """Serializer for confirming phone verification."""
    code = serializers.CharField(max_length=6)
    phone_number = serializers.CharField(max_length=20)

    def validate(self, attrs):
        """Validate verification code."""
        code = attrs.get('code')
        phone_number = attrs.get('phone_number')
        user = self.context['request'].user

        try:
            verification = PhoneVerification.objects.get(
                user=user,
                phone_number=phone_number,
                is_verified=False,
                is_expired=False
            )

            if verification.attempts >= verification.max_attempts:
                raise serializers.ValidationError("Too many attempts. Please request a new code.")

            if verification.code != code:
                verification.increment_attempt()
                raise serializers.ValidationError("Invalid verification code.")

            if verification.is_expired():
                raise serializers.ValidationError("Verification code has expired.")

            attrs['verification'] = verification
            return attrs

        except PhoneVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired verification code.")


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""
    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate email exists."""
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("No account found with this email.")
        return value

    def create(self, validated_data):
        """Create password reset token."""
        email = validated_data['email']
        user = CustomUser.objects.get(email=email)
        token = generate_secret_key(64)
        expires_at = timezone.now() + timedelta(hours=2)

        # Invalidate existing tokens
        PasswordResetToken.objects.filter(user=user, is_used=False).update(
            is_used=True
        )

        return PasswordResetToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_token(self, value):
        """Validate reset token."""
        try:
            token = PasswordResetToken.objects.get(
                token=value,
                is_used=False
            )
            if token.is_expired():
                raise serializers.ValidationError("Reset token has expired.")
            return token
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token.")

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def save(self):
        """Reset user password."""
        token = self.validated_data['token']
        new_password = self.validated_data['new_password']
        user = token.user

        user.set_password(new_password)
        user.save()

        # Mark token as used
        token.use()

        return user


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth authentication."""
    access_token = serializers.CharField()

    def validate_access_token(self, value):
        """Validate Google access token."""
        import requests

        try:
            # Verify token with Google
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                params={'access_token': value}
            )

            if response.status_code != 200:
                raise serializers.ValidationError("Invalid Google access token.")

            user_data = response.json()
            return user_data

        except requests.RequestException:
            raise serializers.ValidationError("Error verifying Google access token.")


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        """Validate old password."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def save(self):
        """Change user password."""
        user = self.context['request'].user
        new_password = self.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        return user


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""

    class Meta:
        model = UserProfile
        fields = (
            'timezone', 'demo_trading_enabled',
            'email_notifications', 'sms_notifications',
            'push_notifications', 'trading_preferences'
        )

    def validate_trading_preferences(self, value):
        """Validate trading preferences JSON."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Trading preferences must be a valid JSON object.")
        return value


class RefreshTokenSerializer(serializers.Serializer):
    """Serializer for refreshing JWT tokens."""
    refresh_token = serializers.CharField()

    def validate_refresh_token(self, value):
        """Validate refresh token."""
        try:
            token = RefreshToken(value)
            return token
        except Exception:
            raise serializers.ValidationError("Invalid refresh token.")