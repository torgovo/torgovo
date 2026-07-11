import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from apps.referrals.models import Referral
from apps.referrals.views import ReferralRegistrationMixin


@pytest.mark.django_db
class TestMyReferralStatsView:
    def test_stats_no_referrals(self, auth_client, user):
        url = reverse('referrals:my-referral-stats')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'referral_code' in response.data
        assert response.data['total_referrals'] == 0
        assert response.data['total_bonus_usdt'] == '0'
        assert 'referral_link' in response.data

    def test_stats_with_referrals(self, auth_client, user, admin_user):
        Referral.objects.create(
            referrer=user, referred_user=admin_user,
            code='TOR000001', bonus_amount=Decimal('50'),
            status='paid',
        )
        url = reverse('referrals:my-referral-stats')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['total_referrals'] == 1
        assert Decimal(response.data['total_bonus_usdt']) == Decimal('50')

    def test_stats_code_persists(self, auth_client, user):
        url = reverse('referrals:my-referral-stats')
        response1 = auth_client.get(url)
        code1 = response1.data['referral_code']

        response2 = auth_client.get(url)
        assert response2.data['referral_code'] == code1

    def test_unauthenticated(self, api_client):
        url = reverse('referrals:my-referral-stats')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestApplyReferralCodeView:
    def test_apply_valid_code(self, auth_client, user, admin_user):
        ref = Referral.objects.create(
            referrer=admin_user,
            referred_user=admin_user,
            code='TORADMIN1',
        )
        url = reverse('referrals:apply-referral-code')
        response = auth_client.post(url, {'referral_code': 'TORADMIN1'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['message'] == 'Referral code applied successfully'

        ref.refresh_from_db()
        assert ref.referred_user == user

    def test_apply_own_code_fails(self, auth_client, user):
        Referral.objects.create(
            referrer=user,
            referred_user=user,
            code='TORSELF',
        )
        url = reverse('referrals:apply-referral-code')
        response = auth_client.post(url, {'referral_code': 'TORSELF'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'own referral code' in response.data['error']

    def test_apply_twice_fails(self, auth_client, user, admin_user):
        ref = Referral.objects.create(
            referrer=admin_user,
            referred_user=admin_user,
            code='TORADMIN2',
        )
        ref.referred_user = user
        ref.save()

        url = reverse('referrals:apply-referral-code')
        response = auth_client.post(url, {'referral_code': 'TORADMIN2'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already applied' in response.data['error']

    def test_invalid_code(self, auth_client):
        url = reverse('referrals:apply-referral-code')
        response = auth_client.post(url, {'referral_code': 'INVALID_CODE'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid' in response.data['error']

    def test_missing_code(self, auth_client):
        url = reverse('referrals:apply-referral-code')
        response = auth_client.post(url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated(self, api_client):
        url = reverse('referrals:apply-referral-code')
        response = api_client.post(url, {'referral_code': 'TEST'}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestReferralRegistrationMixin:
    def test_apply_referral_after_registration_success(self, user, admin_user):
        ref = Referral.objects.create(
            referrer=admin_user,
            referred_user=admin_user,
            code='REGCODE1',
        )
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, 'REGCODE1')
        assert result is not None
        assert result['referral_applied'] is True
        ref.refresh_from_db()
        assert ref.referred_user == user

    def test_apply_referral_no_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, None)
        assert result is None

    def test_apply_referral_empty_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, '')
        assert result is None

    def test_apply_referral_self_referral_skipped(self, user, admin_user):
        ref = Referral.objects.create(
            referrer=admin_user,
            referred_user=admin_user,
            code='SELFREF',
        )
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(admin_user, 'SELFREF')
        assert result is None
        ref.refresh_from_db()
        assert ref.referred_user == admin_user

    def test_apply_referral_invalid_code(self, user):
        mixin = ReferralRegistrationMixin()
        result = mixin.apply_referral_after_registration(user, 'NONEXISTENT')
        assert result is None
