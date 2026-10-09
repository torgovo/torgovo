"""
Authentication models for Torgovo Crypto Trading Platform
Compatible with users.CustomUser as AUTH_USER_MODEL
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class EmailVerification(TimeStampedModel):
    """
    Email verification tokens.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # FIXED: Restored proper reference
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    token = models.CharField(max_length=64, unique=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "auth_email_verifications"
        indexes = [
            models.Index(fields=["user", "token"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {'Verified' if self.is_verified else 'Pending'}"

    def is_expired(self):
        """Check if verification token has expired."""
        return timezone.now() > self.expires_at

    def verify(self):
        """Mark email as verified."""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save()

        self.user.is_email_verified = True
        self.user.save()


class PhoneVerification(TimeStampedModel):
    """
    Phone verification codes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # FIXED: Restored proper reference
        on_delete=models.CASCADE,
        related_name="phone_verifications",
    )
    code = models.CharField(max_length=128)
    phone_number = models.CharField(max_length=20)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "auth_phone_verifications"
        indexes = [
            models.Index(fields=["user", "phone_number"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.phone_number}"

    def is_expired(self):
        """Check if verification code has expired."""
        return timezone.now() > self.expires_at

    def has_attempts_left(self):
        """Check if user has attempts left."""
        return self.attempts < self.max_attempts

    def increment_attempt(self):
        """Increment attempt counter."""
        self.attempts += 1
        self.save()

    def verify(self):
        """Mark phone number as verified."""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save()

        self.user.is_phone_verified = True
        self.user.phone_number = self.phone_number
        self.user.save()


class PasswordResetToken(TimeStampedModel):
    """
    Password reset tokens.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # FIXED: Restored proper reference
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=64, unique=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "auth_password_reset_tokens"
        indexes = [
            models.Index(fields=["user", "token"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {'Used' if self.is_used else 'Pending'}"

    def is_expired(self):
        """Check if reset token has expired."""
        return timezone.now() > self.expires_at

    def use(self):
        """Mark token as used."""
        self.is_used = True
        self.used_at = timezone.now()
        self.save()


class LoginAttempt(TimeStampedModel):
    """
    Track login attempts for security monitoring.
    """

    username = models.CharField(max_length=254)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    was_successful = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "auth_login_attempts"
        indexes = [
            models.Index(fields=["username", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["was_successful"]),
        ]

    def __str__(self):
        outcome = "Success" if self.was_successful else "Failed"
        return f"{self.username} - {self.ip_address} - {outcome}"
