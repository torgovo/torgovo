"""
Signals for authentication app
"""

import logging
import secrets
import string

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.mail import send_mail
from django.dispatch import receiver

from core.utils import get_client_ip

logger = logging.getLogger(__name__)


def generate_otp_code(length=6):
    """Generate OTP code using a cryptographically secure RNG.

    SECURITY (S-2): random.choices() (Mersenne Twister) is predictable; a
    leaked timestamp+seed window could let an attacker brute-force OTPs.
    secrets.choice() reads from the OS CSPRNG.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log user login activity."""
    try:
        from core.models import UserActivityLog

        UserActivityLog.objects.create(
            user=user,
            action="login",
            description=f"User {user.email} logged in",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            endpoint=request.path,
            method=request.method,
            status_code=200,
        )
    except Exception as e:
        logger.warning("Failed to log login activity: %s", e)


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout activity."""
    try:
        from core.models import UserActivityLog

        UserActivityLog.objects.create(
            user=user,
            action="logout",
            description=f"User {user.email} logged out",
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            endpoint=request.path,
            method=request.method,
            status_code=200,
        )
    except Exception as e:
        logger.warning("Failed to log logout activity: %s", e)


def send_welcome_email(user):
    """Send welcome email to new user."""
    subject = "Welcome to Torgovo!"
    message = f"""
    Hello {user.first_name},

    Welcome to Torgovo Crypto Trading Platform!

    Your account has been created successfully. You can now:
    - Set up trading bots
    - Connect to multiple exchanges
    - Receive trading signals
    - Manage your portfolio

    If you have any questions, feel free to contact our support team.

    Best regards,
    Torgovo Team
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error("Failed to send welcome email: %s", e)
