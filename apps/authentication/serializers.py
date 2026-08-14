"""
Serializers for authentication app
"""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.referrals.models import Referral

# Import CustomUser from users app (AUTH_USER_MODEL = 'users.CustomUser')
from apps.users.models import CustomUser
from core.utils import generate_secret_key

from .models import EmailVerification, PasswordResetToken, PhoneVerification


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(
        required=False, allow_blank=True, max_length=20, write_only=True
    )

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone_number",
            "referral_code",
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

    def validate_referral_code(self, value):
        """Validate that the referral code exists in the system."""
        if not value:
            return value
        normalized = value.upper().strip()
        if not Referral.objects.filter(code=normalized).exists():
            raise serializers.ValidationError("Invalid referral code.")
        return normalized

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def create(self, validated_data):
        """Create user and profile."""
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        referral_code = validated_data.pop("referral_code", "")

        user = CustomUser.objects.create_user(password=password, **validated_data)

        # Store referral_code on instance for the view to process after save
        self._referral_code = referral_code

        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate credentials."""
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(
                request=self.context.get("request"), username=email, password=password
            )

            if not user:
                raise serializers.ValidationError("Invalid credentials.")

            if not user.is_active:
                raise serializers.ValidationError("User account is disabled.")

            attrs["user"] = user
            return attrs
        else:
            raise serializers.ValidationError("Must include email and password.")


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user data."""

    full_name = serializers.ReadOnlyField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
            "last_login",
            "timezone",
            "two_factor_enabled",
            "subscription_plan",
            "max_bots_allowed",
            "is_subscription_active",
            "referral_code",
            "total_trades_executed",
            "total_volume_traded",
        )
        read_only_fields = (
            "id",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
            "last_login",
            "two_factor_enabled",
        )


class EmailVerificationSerializer(serializers.ModelSerializer):
    """Serializer for email verification."""

    class Meta:
        model = EmailVerification
        fields = ("user", "token", "expires_at")
        read_only_fields = ("token", "expires_at")

    def create(self, validated_data):
        """Create email verification token."""
        user = validated_data["user"]
        token = generate_secret_key(64)
        expires_at = timezone.now() + timedelta(hours=24)

        # Invalidate existing tokens
        EmailVerification.objects.filter(user=user, is_verified=False).update(is_verified=True)

        return EmailVerification.objects.create(user=user, token=token, expires_at=expires_at)


class PhoneVerificationSerializer(serializers.Serializer):
    """Serializer for phone verification."""

    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value):
        """Validate phone number format."""
        import re

        if not re.match(r"^\+?1?\d{9,15}$", value):
            raise serializers.ValidationError("Invalid phone number format.")
        return value

    def create(self, validated_data):
        """Create phone verification code."""
        from apps.authentication.signals import generate_otp_code

        user = self.context["request"].user
        phone_number = validated_data["phone_number"]
        code = generate_otp_code()
        expires_at = timezone.now() + timedelta(minutes=10)

        # Invalidate existing codes
        PhoneVerification.objects.filter(user=user, is_verified=False).update(is_verified=True)

        return PhoneVerification.objects.create(
            user=user, code=code, phone_number=phone_number, expires_at=expires_at
        )


class PhoneVerificationConfirmSerializer(serializers.Serializer):
    """Serializer for confirming phone verification."""

    code = serializers.CharField(max_length=6)
    phone_number = serializers.CharField(max_length=20)

    def validate(self, attrs):
        """Validate verification code."""
        code = attrs.get("code")
        phone_number = attrs.get("phone_number")
        user = self.context["request"].user

        try:
            verification = PhoneVerification.objects.get(
                user=user,
                phone_number=phone_number,
                is_verified=False,
                expires_at__gt=timezone.now(),
            )

            if verification.attempts >= verification.max_attempts:
                raise serializers.ValidationError("Too many attempts. Please request a new code.")

            if verification.code != code:
                verification.increment_attempt()
                raise serializers.ValidationError("Invalid verification code.")

            if verification.is_expired():
                raise serializers.ValidationError("Verification code has expired.")

            attrs["verification"] = verification
            return attrs

        except PhoneVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired verification code.")


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request.

    SECURITY: Do NOT reveal whether the email exists. We only validate the
    email format here; the view performs the (best-effort) token creation
    and always returns the same generic response.
    """

    email = serializers.EmailField()

    class _NoOp:
        """Sentinel returned from ``save()`` to satisfy DRF's expectation
        that the serializer instance is non-None."""

        user = None
        expires_at = None

    def create(self, validated_data):
        email = validated_data["email"]
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return self._NoOp()
        token = generate_secret_key(64)
        expires_at = timezone.now() + timedelta(hours=2)

        # Invalidate existing tokens
        PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

        return PasswordResetToken.objects.create(user=user, token=token, expires_at=expires_at)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""

    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_token(self, value):
        """Validate reset token exists and is not expired.

        SECURITY (CRIT-4): We only check existence here. The actual is_used
        check + claim is done atomically in save() with select_for_update()
        to prevent race-condition double-use.
        """
        try:
            token = PasswordResetToken.objects.get(token=value)
            if token.is_used:
                raise serializers.ValidationError("Reset token has already been used.")
            if token.is_expired():
                raise serializers.ValidationError("Reset token has expired.")
            # Store raw token string for atomic claim in save()
            return value
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token.")

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def save(self):
        """Reset user password with atomic token claim.

        SECURITY (CRIT-4): select_for_update() acquires a row-level lock,
        preventing a concurrent request from reading is_used=False at the
        same time. Only one request can claim the token.
        """
        from django.db import transaction

        token_value = self.validated_data["token"]
        new_password = self.validated_data["new_password"]

        with transaction.atomic():
            try:
                token = PasswordResetToken.objects.select_for_update().get(
                    token=token_value,
                    is_used=False,
                )
            except PasswordResetToken.DoesNotExist:
                raise serializers.ValidationError(
                    {"token": "Token has already been used or is invalid."}
                )

            if token.is_expired():
                raise serializers.ValidationError({"token": "Reset token has expired."})

            user = token.user
            user.set_password(new_password)
            user.save(update_fields=["password"])

            # Atomically mark as used inside the same transaction
            token.use()

        return user


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth authentication."""

    access_token = serializers.CharField()

    def validate_access_token(self, value):
        """Validate Google access token with audience check.

        SECURITY: We MUST verify the token was issued for *our* application
        (client_id). Without this, any Google access token from any app could
        be used to impersonate a user on Torgovo (CRIT-1 in security audit v2).
        """
        import requests
        from django.conf import settings

        google_client_id = getattr(
            settings, "GOOGLE_CLIENT_ID", ""
        ) or settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {}).get("client_id", "")

        try:
            # Step 1: Verify token audience with Google tokeninfo
            tokeninfo_resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": value},
                timeout=10,
            )
            if tokeninfo_resp.status_code != 200:
                raise serializers.ValidationError("Invalid Google access token.")

            tokeninfo = tokeninfo_resp.json()

            # Audience check — reject tokens issued for other applications
            if google_client_id and tokeninfo.get("aud") != google_client_id:
                raise serializers.ValidationError(
                    "Token audience mismatch — token was not issued for this application."
                )

            # Step 2: Fetch user profile info
            userinfo_resp = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                params={"access_token": value},
                timeout=10,
            )
            if userinfo_resp.status_code != 200:
                raise serializers.ValidationError("Failed to fetch user info from Google.")

            user_data = userinfo_resp.json()
            if not user_data.get("email"):
                raise serializers.ValidationError("Google account has no email.")

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
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def save(self):
        """Change user password."""
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save()
        return user


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
