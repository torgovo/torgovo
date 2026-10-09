from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import (
    EmailVerification,
    LoginAttempt,
    PasswordResetToken,
    PhoneVerification,
)
from apps.users.models import CustomUser

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestUserRegistration:
    url = "/api/auth/register/"

    def test_registration_success(self, api_client):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "first_name": "New",
            "last_name": "User",
            "terms_accepted": True,
            "privacy_policy_accepted": True,
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert (
            response.data["message"]
            == "Registration successful. Please check your email for verification."
        )
        assert "user" in response.data
        assert "tokens" in response.data
        assert response.data["verification_sent"] is True
        assert response.data["user"]["email"] == "newuser@example.com"
        assert CustomUser.objects.filter(email="newuser@example.com").exists()

    def test_registration_without_consent_rejected(self, api_client):
        """COMPLIANCE Phase-1: missing consent booleans -> 400, no user created."""
        data = {
            "username": "noconsent",
            "email": "noconsent@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not CustomUser.objects.filter(email="noconsent@example.com").exists()

    def test_registration_declined_privacy_policy_rejected(self, api_client):
        """COMPLIANCE Phase-1: explicit privacy-policy refusal -> 400."""
        data = {
            "username": "opposer",
            "email": "opposer@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "terms_accepted": True,
            "privacy_policy_accepted": False,
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not CustomUser.objects.filter(email="opposer@example.com").exists()

    def test_registration_stamps_consent_metadata(self, api_client):
        """COMPLIANCE Phase-1: successful registration records consent timestamp + version."""
        from django.conf import settings

        data = {
            "username": "consented",
            "email": "consented@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "terms_accepted": True,
            "privacy_policy_accepted": True,
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        user = CustomUser.objects.get(email="consented@example.com")
        assert user.terms_accepted_at is not None
        assert user.terms_accepted_at <= timezone.now()
        assert user.privacy_version == settings.PRIVACY_POLICY_VERSION

    def test_registration_duplicate_email(self, api_client, user):
        data = {
            "username": "anotheruser",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_duplicate_username(self, api_client, user):
        data = {
            "username": "testuser",
            "email": "unique@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_password_mismatch(self, api_client):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass456!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_missing_fields(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_weak_password(self, api_client):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "123",
            "password_confirm": "123",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_registration_creates_email_verification(self, api_client):
        data = {
            "username": "verifyuser",
            "email": "verify@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "terms_accepted": True,
            "privacy_policy_accepted": True,
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        user = CustomUser.objects.get(email="verify@example.com")
        assert EmailVerification.objects.filter(user=user, is_verified=False).exists()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestUserLogin:
    url = "/api/auth/login/"

    def test_login_success(self, api_client, user):
        user.set_password("CorrectPass123!")
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "tokens" in response.data
        assert "access_token" in response.data["tokens"]
        assert "refresh_token" in response.data["tokens"]
        assert response.data["message"] == "Login successful."
        assert response.data["user"]["email"] == "test@example.com"

    def test_login_creates_login_attempt_success(self, api_client, user):
        user.set_password("CorrectPass123!")
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        api_client.post(self.url, data, format="json")
        assert LoginAttempt.objects.filter(was_successful=True).count() == 1

    def test_login_invalid_credentials(self, api_client, user):
        data = {"email": "test@example.com", "password": "wrongpass"}
        response = api_client.post(self.url, data, format="json")
        # Secure response is 401 with a generic message (no enumeration).
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_fields(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        # Missing fields path is also flattened into the generic 401.
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_disabled_user(self, api_client, user):
        user.set_password("CorrectPass123!")
        user.save()
        user.is_active = False
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_email(self, api_client):
        data = {"email": "nobody@example.com", "password": "somepass"}
        response = api_client.post(self.url, data, format="json")
        # Same response shape as wrong-password to defeat user enumeration.
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestUserLogout:
    url = "/api/auth/logout/"

    def test_logout_authenticated(self, auth_client, user):
        refresh = RefreshToken.for_user(user)
        response = auth_client.post(self.url, {"refresh_token": str(refresh)}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Logout successful."

    def test_logout_unauthenticated(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_with_valid_token(self, auth_client, user):
        refresh = RefreshToken.for_user(user)
        response = auth_client.post(self.url, {"refresh_token": str(refresh)}, format="json")
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# User Detail
# ---------------------------------------------------------------------------


class TestUserDetailView:
    url = "/api/auth/user/"

    def test_get_user_authenticated(self, auth_client, user):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "test@example.com"
        assert response.data["username"] == "testuser"
        assert response.data["subscription_plan"] == "free"

    def test_get_user_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_patch_user(self, auth_client):
        response = auth_client.patch(
            self.url, {"first_name": "John", "last_name": "Doe"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "John"
        assert response.data["last_name"] == "Doe"

    def test_patch_read_only_fields(self, auth_client, user):
        response = auth_client.patch(self.url, {"is_email_verified": True}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_email_verified"] is False


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------


class TestEmailVerificationRequest:
    url = "/api/auth/verify-email/"

    def test_send_verification_email(self, auth_client, user):
        response = auth_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Verification email sent."
        assert "expires_at" in response.data

    def test_unauthenticated(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_already_verified(self, auth_client, user):
        user.is_email_verified = True
        user.save()
        response = auth_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already verified" in response.data["message"].lower()


class TestEmailVerificationConfirm:
    def test_verify_valid_token(self, api_client, user):
        ev = EmailVerification.objects.create(
            user=user, token="validemailtoken123", expires_at=timezone.now() + timedelta(hours=24)
        )
        response = api_client.get(f"/api/auth/verify-email/{ev.token}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Email verified successfully."
        ev.refresh_from_db()
        assert ev.is_verified is True
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_verify_invalid_token(self, api_client):
        response = api_client.get("/api/auth/verify-email/invalidtoken123/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_TOKEN"

    def test_verify_expired_token(self, api_client, user):
        ev = EmailVerification.objects.create(
            user=user, token="expiredemailtoken", expires_at=timezone.now() - timedelta(hours=1)
        )
        response = api_client.get(f"/api/auth/verify-email/{ev.token}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "TOKEN_EXPIRED"

    def test_verify_already_used_token(self, api_client, user):
        ev = EmailVerification.objects.create(
            user=user,
            token="usedemailtoken123",
            expires_at=timezone.now() + timedelta(hours=24),
            is_verified=True,
            verified_at=timezone.now(),
        )
        response = api_client.get(f"/api/auth/verify-email/{ev.token}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_TOKEN"


# ---------------------------------------------------------------------------
# Phone Verification
# ---------------------------------------------------------------------------


class TestPhoneVerificationRequest:
    url = "/api/auth/verify-phone/"

    def test_send_verification_code(self, auth_client):
        data = {"phone_number": "+1234567890"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "expires_at" in response.data

    def test_unauthenticated(self, api_client):
        data = {"phone_number": "+1234567890"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_phone_number(self, auth_client):
        data = {"phone_number": "abc"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestPhoneVerificationConfirm:
    url = "/api/auth/verify-phone/confirm/"

    def test_confirm_valid_code(self, auth_client, user):
        PhoneVerification.objects.create(
            user=user,
            code=make_password("123456"),
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        data = {"code": "123456", "phone_number": "+1234567890"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Phone number verified successfully."
        user.refresh_from_db()
        assert user.is_phone_verified is True
        assert user.phone_number == "+1234567890"

    def test_confirm_wrong_code(self, auth_client, user):
        PhoneVerification.objects.create(
            user=user,
            code=make_password("123456"),
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        data = {"code": "000000", "phone_number": "+1234567890"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_unauthenticated(self, api_client):
        data = {"code": "123456", "phone_number": "+1234567890"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_confirm_expired_code(self, auth_client, user):
        PhoneVerification.objects.create(
            user=user,
            code=make_password("123456"),
            phone_number="+1234567890",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        data = {"code": "123456", "phone_number": "+1234567890"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_too_many_attempts(self, auth_client, user):
        PhoneVerification.objects.create(
            user=user,
            code=make_password("123456"),
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
            attempts=3,
        )
        data = {"code": "123456", "phone_number": "+1234567890"}
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------


class TestPasswordResetRequest:
    url = "/api/auth/password-reset/"

    def test_request_reset_valid_email(self, api_client, user):
        data = {"email": "test@example.com"}
        response = api_client.post(self.url, data, format="json")
        # Generic 200 response is now returned in both branches (no leak).
        assert response.status_code == status.HTTP_200_OK
        assert "message" in response.data

    def test_request_reset_nonexistent_email(self, api_client):
        data = {"email": "nobody@example.com"}
        response = api_client.post(self.url, data, format="json")
        # Same generic 200 as the valid-email branch — enumeration-safe.
        assert response.status_code == status.HTTP_200_OK

    def test_request_reset_creates_token(self, api_client, user):
        data = {"email": "test@example.com"}
        api_client.post(self.url, data, format="json")
        assert PasswordResetToken.objects.filter(user=user, is_used=False).count() == 1


class TestPasswordResetConfirm:
    url = "/api/auth/password-reset/confirm/"

    def test_confirm_valid_reset(self, api_client, user):
        prt = PasswordResetToken.objects.create(
            user=user, token="validresettoken123", expires_at=timezone.now() + timedelta(hours=2)
        )
        data = {
            "token": "validresettoken123",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Password reset successful."
        user.refresh_from_db()
        assert user.check_password("NewStrongPass123!")
        prt.refresh_from_db()
        assert prt.is_used is True

    def test_confirm_expired_token(self, api_client, user):
        PasswordResetToken.objects.create(
            user=user, token="expiredresettoken", expires_at=timezone.now() - timedelta(hours=1)
        )
        data = {
            "token": "expiredresettoken",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_invalid_token(self, api_client):
        data = {
            "token": "nonexistenttoken",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_password_mismatch(self, api_client, user):
        PasswordResetToken.objects.create(
            user=user, token="mismatchresettoken", expires_at=timezone.now() + timedelta(hours=2)
        )
        data = {
            "token": "mismatchresettoken",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "DifferentPass456!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_used_token(self, api_client, user):
        PasswordResetToken.objects.create(
            user=user,
            token="usedresettoken123",
            expires_at=timezone.now() + timedelta(hours=2),
            is_used=True,
            used_at=timezone.now(),
        )
        data = {
            "token": "usedresettoken123",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


class TestGoogleAuth:
    url = "/api/auth/google/"

    def _mock_google_responses(
        self, mocker, user_data, tokeninfo_aud="your-google-oauth-client-id"
    ):
        tokeninfo_response = mocker.Mock()
        tokeninfo_response.status_code = 200
        tokeninfo_response.json.return_value = {
            "aud": tokeninfo_aud,
            **user_data,
        }
        userinfo_response = mocker.Mock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = user_data

        def mock_requests_get(url, **kwargs):
            if "tokeninfo" in url:
                return tokeninfo_response
            return userinfo_response

        mocker.patch("requests.get", side_effect=mock_requests_get)

    def test_google_auth_new_user(self, api_client, mocker):
        self._mock_google_responses(
            mocker,
            {
                "email": "googleuser@example.com",
                "name": "Google User",
                "given_name": "Google",
                "family_name": "User",
            },
        )
        data = {"access_token": "valid-google-token"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_new_user"] is True
        assert response.data["user"]["email"] == "googleuser@example.com"
        assert "tokens" in response.data
        assert CustomUser.objects.filter(email="googleuser@example.com").exists()

    def test_google_auth_existing_user(self, api_client, user, mocker):
        user.email = "googleuser@example.com"
        user.save()
        self._mock_google_responses(
            mocker,
            {
                "email": "googleuser@example.com",
                "name": "Existing User",
            },
        )
        data = {"access_token": "valid-google-token"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_new_user"] is False

    def test_google_auth_invalid_token(self, api_client, mocker):
        mock_response = mocker.Mock()
        mock_response.status_code = 401
        mocker.patch("requests.get", return_value=mock_response)
        data = {"access_token": "invalid-token"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_google_auth_missing_token(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_google_auth_new_user_gets_profile(self, api_client, mocker):
        self._mock_google_responses(
            mocker,
            {
                "email": "profilestest@example.com",
                "name": "Profile Test",
            },
        )
        data = {"access_token": "valid-google-token"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        user = CustomUser.objects.get(email="profilestest@example.com")
        assert user.subscription_plan == "free"


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


class TestChangePassword:
    url = "/api/auth/change-password/"

    def test_change_password_success(self, auth_client, user):
        user.set_password("OldPass123!")
        user.save()
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        }
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Password changed successfully."
        user.refresh_from_db()
        assert user.check_password("NewPass456!")

    def test_change_password_unauthenticated(self, api_client):
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        }
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_change_password_wrong_old(self, auth_client, user):
        user.set_password("OldPass123!")
        user.save()
        data = {
            "old_password": "WrongOldPass!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        }
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_mismatch(self, auth_client, user):
        user.set_password("OldPass123!")
        user.save()
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "DifferentPass789!",
        }
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_weak_new(self, auth_client, user):
        user.set_password("OldPass123!")
        user.save()
        data = {
            "old_password": "OldPass123!",
            "new_password": "123",
            "new_password_confirm": "123",
        }
        response = auth_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Refresh Token
# ---------------------------------------------------------------------------


class TestRefreshToken:
    url = "/api/auth/refresh-token/"

    def test_refresh_success(self, api_client, user):
        refresh = RefreshToken.for_user(user)
        data = {"refresh_token": str(refresh)}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.data
        assert response.data["message"] == "Token refreshed successfully."

    def test_refresh_invalid_token(self, api_client):
        data = {"refresh_token": "invalidtoken123"}
        response = api_client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_refresh_missing_token(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Login Attempt Tracking
# ---------------------------------------------------------------------------


class TestLoginAttemptTracking:
    def test_successful_login_creates_attempt(self, api_client, user):
        user.set_password("CorrectPass123!")
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        api_client.post("/api/auth/login/", data, format="json")
        attempt = LoginAttempt.objects.last()
        assert attempt is not None
        assert attempt.username == "test@example.com"
        assert attempt.was_successful is True

    def test_failed_login_creates_attempt(self, api_client, user):
        data = {"email": "test@example.com", "password": "wrongpass"}
        api_client.post("/api/auth/login/", data, format="json")
        attempt = LoginAttempt.objects.last()
        assert attempt is not None
        assert attempt.was_successful is False
