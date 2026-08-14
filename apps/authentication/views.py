"""
Views for authentication app
"""

import logging

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.referrals.models import Referral
from apps.referrals.views import ReferralRegistrationMixin

# Import CustomUser from users app (AUTH_USER_MODEL = 'users.CustomUser')
from apps.users.models import CustomUser
from core.exceptions import TradingBotException
from core.utils import get_client_ip

from .models import EmailVerification, LoginAttempt
from .serializers import (
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    GoogleAuthSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PhoneVerificationConfirmSerializer,
    PhoneVerificationSerializer,
    RefreshTokenSerializer,
    UserLoginSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)

logger = logging.getLogger("apps")


def get_tokens_for_user(user):
    """Generate JWT tokens for user."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh_token": str(refresh),
        "access_token": str(refresh.access_token),
    }


def create_login_attempt(request, success=True, failure_reason=None):
    """Create login attempt record."""
    # SECURITY (HIGH-2): normalize email the same way UserLoginView does,
    # so lockout counts are consistent regardless of case/whitespace.
    raw_email = request.data.get("email", "")
    normalized_email = raw_email.strip().lower() if raw_email else ""
    LoginAttempt.objects.create(
        username=normalized_email,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        was_successful=success,
        failure_reason=failure_reason or "",
    )


class UserRegistrationView(ReferralRegistrationMixin, generics.CreateAPIView):
    """User registration endpoint."""

    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        """Register new user and send verification email."""
        try:
            # Support legacy ?ref= query param — frontend should prefer POST body
            referral_from_query = (request.GET.get("ref", "") or "").upper().strip()

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Determine referral code: POST body takes precedence over ?ref= query param
            referral_code = ""

            if not serializer.validated_data.get("referral_code") and referral_from_query:
                if Referral.objects.filter(code=referral_from_query).exists():
                    referral_code = referral_from_query

            user = serializer.save()

            # For POST body case, the serializer stores the code after create()
            if not referral_code:
                referral_code = getattr(serializer, "_referral_code", "")
            self.apply_referral_after_registration(user, referral_code)

            # Create email verification
            email_verification = EmailVerificationSerializer(data={"user": user.id})
            if email_verification.is_valid():
                email_verification.save()

            # Send verification email (in production, use celery)
            try:
                self.send_verification_email(user, email_verification.instance)
            except Exception as e:
                logger.error(f"Failed to send verification email: {e}")

            # Generate tokens
            tokens = get_tokens_for_user(user)

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Registration successful. Please check your email for verification.",
                    "verification_sent": True,
                },
                status=status.HTTP_201_CREATED,
            )

        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Registration error: {e}")
            raise TradingBotException(
                message=str(e),
                error_code="REGISTRATION_ERROR",
            )

    def send_verification_email(self, user, email_verification):
        """Send verification email to user."""
        verification_url = f"{settings.FRONTEND_URL}/verify-email/{email_verification.token}"
        subject = "Verify Your Torgovo Account"
        message = f"""
        Hello {user.first_name},

        Please click the link below to verify your email address:
        {verification_url}

        This link will expire in 24 hours.

        Best regards,
        Torgovo Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class UserLoginView(APIView):
    """User login endpoint with brute-force lockout."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    # Lockout policy: 5 failed attempts in 15 minutes => 15-min lockout per
    # IP+email pair. Tunable via settings.AUTH_LOCKOUT_THRESHOLD / WINDOW.
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_WINDOW_MINUTES = 15

    def _ip_prefix(self, ip: str) -> str:
        """Extract /24 prefix from an IPv4 address."""
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".0"
        return ip

    def _ua_hash(self, user_agent: str) -> str:
        """Deterministic hash of user-agent for throttle grouping."""
        import hashlib

        return hashlib.sha256((user_agent or "").encode()).hexdigest()[:12]

    def _is_locked_out(self, email, ip, user_agent):
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(minutes=self.LOCKOUT_WINDOW_MINUTES)
        ip_prefix = ".".join(ip.split(".")[:3]) + "."
        ua_prefix = (user_agent or "")[:12]
        failures = LoginAttempt.objects.filter(
            username=email,
            ip_address__startswith=ip_prefix,
            user_agent__startswith=ua_prefix,
            was_successful=False,
            created_at__gte=cutoff,
        ).count()
        return failures >= self.LOCKOUT_THRESHOLD

    def post(self, request):
        """Authenticate user and return tokens."""
        email = (request.data.get("email") or "").strip().lower()
        ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        if email and self._is_locked_out(email, ip, user_agent):
            logger.warning(f"Account locked: {email} from {ip}")
            return Response(
                {
                    "error": {
                        "code": "LOCKED_OUT",
                        "message": "Too many failed attempts. Try again later.",
                    }
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            serializer = UserLoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.validated_data["user"]

            create_login_attempt(request, success=True)
            user.last_login_ip = ip
            user.save(update_fields=["last_login_ip"])

            tokens = get_tokens_for_user(user)
            user_logged_in.send(sender=user.__class__, request=request, user=user)

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Login successful.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            create_login_attempt(request, success=False, failure_reason=type(e).__name__)
            # Generic message to defeat user enumeration
            return Response(
                {"error": {"code": "LOGIN_FAILED", "message": "Invalid credentials."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class UserLogoutView(APIView):
    """User logout endpoint."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Logout user and blacklist refresh token."""
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            # Send logout signal
            user_logged_out.send(sender=request.user.__class__, request=request, user=request.user)

            return Response({"message": "Logout successful."}, status=status.HTTP_200_OK)

        except TokenError:
            return Response(
                {"message": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({"message": "Logout failed."}, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(generics.RetrieveUpdateAPIView):
    """User details endpoint."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """Get current user."""
        return self.request.user


class EmailVerificationView(generics.CreateAPIView):
    """Email verification endpoint."""

    serializer_class = EmailVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """Create and send email verification."""
        try:
            user = request.user
            if user.is_email_verified:
                return Response(
                    {"message": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data={"user": user.id})
            serializer.is_valid(raise_exception=True)
            email_verification = serializer.save()

            # Send verification email
            try:
                self.send_verification_email(user, email_verification)
            except Exception as e:
                logger.error(f"Failed to send verification email: {e}")

            return Response(
                {
                    "message": "Verification email sent.",
                    "expires_at": email_verification.expires_at,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Email verification error: {e}")
            raise TradingBotException(message=str(e), error_code="EMAIL_VERIFICATION_ERROR")

    def send_verification_email(self, user, email_verification):
        """Send verification email."""
        verification_url = f"{settings.FRONTEND_URL}/verify-email/{email_verification.token}"
        subject = "Verify Your Torgovo Account"
        message = f"""
        Hello {user.first_name},

        Please click the link below to verify your email address:
        {verification_url}

        This link will expire in 24 hours.

        Best regards,
        Torgovo Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


@api_view(["GET", "POST"])
@permission_classes([permissions.AllowAny])
def verify_email(request, token):
    """Verify email with token."""
    try:
        try:
            email_verification = EmailVerification.objects.get(token=token, is_verified=False)
        except EmailVerification.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "Invalid or already used verification token.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if email_verification.is_expired():
            return Response(
                {"error": {"code": "TOKEN_EXPIRED", "message": "Verification token has expired."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify email
        email_verification.verify()

        return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return Response(
            {"error": {"code": "VERIFICATION_ERROR", "message": "Email verification failed."}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class PhoneVerificationRequestView(generics.CreateAPIView):
    """Phone verification request endpoint."""

    serializer_class = PhoneVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """Send phone verification code."""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            phone_verification = serializer.save()

            # Send SMS with verification code (in production, use SMS service)
            try:
                self.send_verification_sms(phone_verification)
            except Exception as e:
                logger.error(f"Failed to send verification SMS: {e}")

            return Response(
                {
                    "message": "Verification code sent to your phone.",
                    "expires_at": phone_verification.expires_at,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Phone verification request error: {e}")
            raise TradingBotException(message=str(e), error_code="PHONE_VERIFICATION_ERROR")

    def send_verification_sms(self, phone_verification):
        """Send SMS with verification code."""
        # In production, integrate with SMS service like Twilio
        # SECURITY (CRIT-6): NEVER log the OTP code — only log that SMS was sent.
        # The code is stored hashed in DB; logging it defeats the purpose.
        masked_phone = phone_verification.phone_number[:5] + "***"
        logger.info(f"Verification SMS dispatched to {masked_phone}")


class PhoneVerificationConfirmView(APIView):
    """Phone verification confirmation endpoint."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Confirm phone verification."""
        try:
            serializer = PhoneVerificationConfirmSerializer(
                data=request.data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)

            verification = serializer.validated_data["verification"]
            verification.verify()

            return Response(
                {"message": "Phone number verified successfully."}, status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Phone verification confirmation error: {e}")
            raise TradingBotException(message=str(e), error_code="PHONE_VERIFICATION_CONFIRM_ERROR")


class PasswordResetRequestView(generics.CreateAPIView):
    """Password reset request endpoint."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "password_reset"

    def create(self, request, *args, **kwargs):
        """Request password reset.

        Always returns the same generic response, even for unknown emails,
        to prevent account enumeration.
        """
        generic_response = Response(
            {"message": "If an account exists, a password reset link has been sent."},
            status=status.HTTP_200_OK,
        )
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            password_reset = serializer.save()
            # Only send the email when an actual token was created.
            if getattr(password_reset, "user", None) is not None:
                try:
                    self.send_password_reset_email(password_reset)
                except Exception as e:
                    logger.error(f"Failed to send password reset email: {e}")
            return generic_response
        except Exception as e:
            logger.error(f"Password reset request error: {type(e).__name__}")
            return generic_response

    def send_password_reset_email(self, password_reset):
        """Send password reset email."""
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{password_reset.token}"
        subject = "Reset Your Torgovo Password"
        message = f"""
        Hello {password_reset.user.first_name},

        Please click the link below to reset your password:
        {reset_url}

        This link will expire in 2 hours.

        If you didn't request this password reset, please ignore this email.

        Best regards,
        Torgovo Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[password_reset.user.email],
            fail_silently=False,
        )


class PasswordResetConfirmView(APIView):
    """Password reset confirmation endpoint."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Confirm password reset."""
        try:
            serializer = PasswordResetConfirmSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(
                {
                    "message": "Password reset successful.",
                    # SECURITY (MED-4): Do NOT return user data here — this is
                    # an unauthenticated endpoint. Returning profile info to
                    # anyone with a reset link is a data leak.
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Password reset confirmation error: {e}")
            raise TradingBotException(message=str(e), error_code="PASSWORD_RESET_CONFIRM_ERROR")


class GoogleAuthView(APIView):
    """Google OAuth authentication endpoint."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Authenticate with Google OAuth."""
        try:
            serializer = GoogleAuthSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            google_user_data = serializer.validated_data["access_token"]

            # Find or create user
            user, created = self.get_or_create_google_user(google_user_data)

            # Generate tokens
            tokens = get_tokens_for_user(user)

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Google authentication successful.",
                    "is_new_user": created,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Google auth error: {e}")
            raise TradingBotException(
                message="Google authentication failed.", error_code="GOOGLE_AUTH_ERROR"
            )

    def get_or_create_google_user(self, google_user_data):
        """Get or create user from Google data."""
        email = google_user_data["email"]

        try:
            user = CustomUser.objects.get(email=email)
            return user, False
        except CustomUser.DoesNotExist:
            # Create new user
            user = CustomUser.objects.create_user(
                email=email,
                username=google_user_data.get("name", email.split("@")[0]),
                first_name=google_user_data.get("given_name", ""),
                last_name=google_user_data.get("family_name", ""),
                is_email_verified=True,
            )

            return user, True


class ChangePasswordView(APIView):
    """Change password endpoint. Blacklists all existing refresh tokens."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Change user password and invalidate existing refresh tokens."""
        try:
            serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save()

            # Blacklist all outstanding refresh tokens for this user
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

            OutstandingToken.objects.filter(user=request.user).delete()

            return Response(
                {"message": "Password changed successfully."}, status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Change password error: {e}")
            raise TradingBotException(
                message="Password change failed.", error_code="CHANGE_PASSWORD_ERROR"
            )


class RefreshTokenView(APIView):
    """Refresh JWT token endpoint.

    With ROTATE_REFRESH_TOKENS=True, accessing .access_token rotates the
    refresh token (old is blacklisted). Must return the new refresh_token
    to the client so it can be used next time.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Refresh access + refresh token pair."""
        try:
            serializer = RefreshTokenSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            refresh_token_obj = serializer.validated_data["refresh_token"]

            # This triggers rotation (new refresh token, old blacklisted)
            access_token = str(refresh_token_obj.access_token)
            new_refresh_token = str(refresh_token_obj)

            return Response(
                {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "message": "Token refreshed successfully.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise TradingBotException(
                message="Token refresh failed.", error_code="TOKEN_REFRESH_ERROR"
            )
