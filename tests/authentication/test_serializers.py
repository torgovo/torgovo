from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.authentication.models import EmailVerification, PasswordResetToken, PhoneVerification
from apps.authentication.serializers import (
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

User = get_user_model()


@pytest.mark.django_db
class TestUserRegistrationSerializer:
    def test_valid_registration(self):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "first_name": "New",
            "last_name": "User",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_password_mismatch(self):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass456!",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False
        assert "Passwords" in str(serializer.errors["non_field_errors"])

    def test_duplicate_email(self, user):
        data = {
            "username": "anotheruser",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False
        assert "email" in serializer.errors

    def test_duplicate_username(self, user):
        data = {
            "username": "testuser",
            "email": "unique@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False
        assert "username" in serializer.errors

    def test_duplicate_phone_number(self, user):
        user.phone_number = "+1234567890"
        user.save()
        data = {
            "username": "anotheruser",
            "email": "another@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "phone_number": "+1234567890",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False
        assert "phone_number" in serializer.errors

    def test_create_user_and_profile(self):
        data = {
            "username": "createuser",
            "email": "create@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid()
        user = serializer.save()
        assert User.objects.filter(email="create@example.com").exists()
        assert user.referral_code is not None
        assert user.check_password("StrongPass123!")

    def test_missing_password_confirm(self):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPass123!",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False

    def test_weak_password(self):
        data = {
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "123",
            "password_confirm": "123",
        }
        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestUserLoginSerializer:
    def test_valid_credentials(self, user):
        user.set_password("CorrectPass123!")
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        serializer = UserLoginSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert "user" in serializer.validated_data

    def test_invalid_credentials(self):
        data = {"email": "test@example.com", "password": "wrongpass"}
        serializer = UserLoginSerializer(data=data)
        assert serializer.is_valid() is False

    def test_missing_fields(self):
        serializer = UserLoginSerializer(data={})
        assert serializer.is_valid() is False

    def test_disabled_user(self, user):
        user.set_password("CorrectPass123!")
        user.save()
        user.is_active = False
        user.save()
        data = {"email": "test@example.com", "password": "CorrectPass123!"}
        serializer = UserLoginSerializer(data=data)
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestUserSerializer:
    def test_user_serialization(self, user):
        serializer = UserSerializer(user)
        data = serializer.data
        assert data["email"] == user.email
        assert data["username"] == user.username
        assert data["is_email_verified"] is False
        assert data["subscription_plan"] == "free"

    def test_user_serialization_read_only_fields(self, user):
        serializer = UserSerializer(user, data={"is_email_verified": True}, partial=True)
        assert serializer.is_valid()
        serializer.save()
        user.refresh_from_db()
        assert user.is_email_verified is False

    def test_full_name_read_only(self, user):
        user.first_name = "John"
        user.last_name = "Doe"
        user.save()
        serializer = UserSerializer(user)
        assert serializer.data["full_name"] == "John Doe"


@pytest.mark.django_db
class TestEmailVerificationSerializer:
    def test_create_email_verification(self, user):
        data = {"user": user.id}
        serializer = EmailVerificationSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        ev = serializer.save()
        assert ev.user == user
        assert len(ev.token) > 0
        assert ev.expires_at > timezone.now()

    def test_token_is_read_only(self):
        serializer = EmailVerificationSerializer()
        assert "token" in serializer.get_fields()
        assert serializer.get_fields()["token"].read_only is True

    def test_expires_at_is_read_only(self):
        serializer = EmailVerificationSerializer()
        assert serializer.get_fields()["expires_at"].read_only is True

    def test_invalidates_old_tokens(self, user):
        old_ev = EmailVerification.objects.create(
            user=user,
            token="oldtoken123456789012345678901234567890123456789012345678901234",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        serializer = EmailVerificationSerializer(data={"user": user.id})
        assert serializer.is_valid()
        serializer.save()
        old_ev.refresh_from_db()
        assert old_ev.is_verified is True


@pytest.mark.django_db
class TestPhoneVerificationSerializer:
    def test_valid_phone_number(self):
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = None
        data = {"phone_number": "+1234567890"}
        serializer = PhoneVerificationSerializer(data=data, context={"request": request})
        assert serializer.is_valid(), serializer.errors

    def test_invalid_phone_number(self):
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = None
        data = {"phone_number": "abc"}
        serializer = PhoneVerificationSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_create_verification(self, user):
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"phone_number": "+1234567890"}
        serializer = PhoneVerificationSerializer(data=data, context={"request": request})
        assert serializer.is_valid(), serializer.errors
        pv = serializer.save()
        assert pv.user == user
        assert pv.phone_number == "+1234567890"
        assert len(pv.code) == 6
        assert pv.code.isdigit()
        assert pv.expires_at > timezone.now()

    def test_invalidates_old_codes(self, user):
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        old_pv = PhoneVerification.objects.create(
            user=user,
            code="000000",
            phone_number="+1987654321",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        data = {"phone_number": "+1234567890"}
        serializer = PhoneVerificationSerializer(data=data, context={"request": request})
        assert serializer.is_valid()
        serializer.save()
        old_pv.refresh_from_db()
        assert old_pv.is_verified is True


@pytest.mark.django_db
class TestPhoneVerificationConfirmSerializer:
    def test_valid_code(self, user):
        pv = PhoneVerification.objects.create(
            user=user,
            code="123456",
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "123456", "phone_number": "+1234567890"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["verification"] == pv

    def test_wrong_code(self, user):
        PhoneVerification.objects.create(
            user=user,
            code="123456",
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "000000", "phone_number": "+1234567890"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_expired_code(self, user):
        PhoneVerification.objects.create(
            user=user,
            code="123456",
            phone_number="+1234567890",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "123456", "phone_number": "+1234567890"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_too_many_attempts(self, user):
        PhoneVerification.objects.create(
            user=user,
            code="123456",
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
            attempts=3,
        )
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "123456", "phone_number": "+1234567890"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_wrong_code_increments_attempts(self, user):
        pv = PhoneVerification.objects.create(
            user=user,
            code="123456",
            phone_number="+1234567890",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "000000", "phone_number": "+1234567890"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False
        pv.refresh_from_db()
        assert pv.attempts == 1

    def test_nonexistent_verification(self, user):
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {"code": "123456", "phone_number": "+9999999999"}
        serializer = PhoneVerificationConfirmSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestPasswordResetRequestSerializer:
    def test_valid_email(self, user):
        data = {"email": "test@example.com"}
        serializer = PasswordResetRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_nonexistent_email(self):
        """Unknown email must NOT raise validation error (defeats user
        enumeration). The serializer accepts the email and ``save()``
        returns a no-op sentinel (``user=None``) instead of creating a token."""
        data = {"email": "nonexistent@example.com"}
        serializer = PasswordResetRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        result = serializer.save()
        assert getattr(result, "user", "missing") is None

    def test_create_token(self, user):
        data = {"email": "test@example.com"}
        serializer = PasswordResetRequestSerializer(data=data)
        assert serializer.is_valid()
        prt = serializer.save()
        assert prt.user == user
        assert len(prt.token) > 0
        assert prt.expires_at > timezone.now()

    def test_invalidates_old_tokens(self, user):
        old_prt = PasswordResetToken.objects.create(
            user=user,
            token="oldresettokendatadatadatadatadatadatada",
            expires_at=timezone.now() + timedelta(hours=2),
        )
        data = {"email": "test@example.com"}
        serializer = PasswordResetRequestSerializer(data=data)
        assert serializer.is_valid()
        serializer.save()
        old_prt.refresh_from_db()
        assert old_prt.is_used is True


@pytest.mark.django_db
class TestPasswordResetConfirmSerializer:
    def test_valid_reset(self, user):
        prt = PasswordResetToken.objects.create(
            user=user, token="validresettoken123", expires_at=timezone.now() + timedelta(hours=2)
        )
        data = {
            "token": "validresettoken123",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        result_user = serializer.save()
        assert result_user == user
        # Re-fetch from DB; the ``user`` fixture object holds the original
        # in-memory password hash and won't reflect the change.
        user.refresh_from_db()
        assert user.check_password("NewStrongPass123!")
        prt.refresh_from_db()
        assert prt.is_used is True

    def test_expired_token(self, user):
        PasswordResetToken.objects.create(
            user=user, token="expiredtoken12345", expires_at=timezone.now() - timedelta(hours=1)
        )
        data = {
            "token": "expiredtoken12345",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid() is False

    def test_invalid_token(self):
        data = {
            "token": "nonexistenttoken",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid() is False

    def test_password_mismatch(self, user):
        PasswordResetToken.objects.create(
            user=user, token="mismatchtoken1234", expires_at=timezone.now() + timedelta(hours=2)
        )
        data = {
            "token": "mismatchtoken1234",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "DifferentPass456!",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid() is False

    def test_used_token(self, user):
        PasswordResetToken.objects.create(
            user=user,
            token="usedtoken1234567",
            expires_at=timezone.now() + timedelta(hours=2),
            is_used=True,
            used_at=timezone.now(),
        )
        data = {
            "token": "usedtoken1234567",
            "new_password": "NewStrongPass123!",
            "new_password_confirm": "NewStrongPass123!",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid() is False

    def test_weak_password(self, user):
        PasswordResetToken.objects.create(
            user=user, token="weakpasswordtoken", expires_at=timezone.now() + timedelta(hours=2)
        )
        data = {
            "token": "weakpasswordtoken",
            "new_password": "123",
            "new_password_confirm": "123",
        }
        serializer = PasswordResetConfirmSerializer(data=data)
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestGoogleAuthSerializer:
    def test_validate_access_token_calls_google(self, mocker):
        tokeninfo_response = mocker.Mock()
        tokeninfo_response.status_code = 200
        tokeninfo_response.json.return_value = {
            "aud": "your-google-oauth-client-id",
            "email": "google@example.com",
            "name": "Google User",
        }
        userinfo_response = mocker.Mock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "email": "google@example.com",
            "name": "Google User",
        }

        def mock_requests_get(url, **kwargs):
            if "tokeninfo" in url:
                return tokeninfo_response
            if "userinfo" in url:
                return userinfo_response
            return tokeninfo_response

        mocker.patch("requests.get", side_effect=mock_requests_get)
        serializer = GoogleAuthSerializer(data={"access_token": "valid-google-token"})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["access_token"]["email"] == "google@example.com"

    def test_invalid_google_token(self, mocker):
        mock_response = mocker.Mock()
        mock_response.status_code = 401
        mocker.patch("requests.get", return_value=mock_response)
        serializer = GoogleAuthSerializer(data={"access_token": "invalid-token"})
        assert serializer.is_valid() is False

    def test_google_api_error(self, mocker):
        import requests

        mocker.patch("requests.get", side_effect=requests.ConnectionError("Connection error"))
        serializer = GoogleAuthSerializer(data={"access_token": "error-token"})
        assert serializer.is_valid() is False

    def test_missing_access_token(self):
        serializer = GoogleAuthSerializer(data={})
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestChangePasswordSerializer:
    def test_valid_password_change(self, user):
        user.set_password("OldPass123!")
        user.save()
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        }
        serializer = ChangePasswordSerializer(data=data, context={"request": request})
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        user.refresh_from_db()
        assert user.check_password("NewPass456!")

    def test_wrong_old_password(self, user):
        user.set_password("OldPass123!")
        user.save()
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {
            "old_password": "WrongOldPass!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        }
        serializer = ChangePasswordSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_password_mismatch(self, user):
        user.set_password("OldPass123!")
        user.save()
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "DifferentPass789!",
        }
        serializer = ChangePasswordSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False

    def test_weak_new_password(self, user):
        user.set_password("OldPass123!")
        user.save()
        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user
        data = {
            "old_password": "OldPass123!",
            "new_password": "123",
            "new_password_confirm": "123",
        }
        serializer = ChangePasswordSerializer(data=data, context={"request": request})
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestRefreshTokenSerializer:
    def test_valid_refresh_token(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user)
        data = {"refresh_token": str(token)}
        serializer = RefreshTokenSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["refresh_token"] is not None

    def test_invalid_refresh_token(self):
        data = {"refresh_token": "invalidtoken"}
        serializer = RefreshTokenSerializer(data=data)
        assert serializer.is_valid() is False

    def test_expired_refresh_token(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken()
        token.set_exp(lifetime=timedelta(seconds=-1))
        data = {"refresh_token": str(token)}
        serializer = RefreshTokenSerializer(data=data)
        assert serializer.is_valid() is False
