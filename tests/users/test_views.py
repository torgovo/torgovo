import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# User List (Admin only)
# ---------------------------------------------------------------------------

class TestUserListView:
    url = '/api/users/admin/'

    def test_list_users_as_admin(self, admin_client, user):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data

    def test_list_users_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_users_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_users_contains_users(self, admin_client, user):
        response = admin_client.get(self.url)
        results = response.data['results']
        emails = [u['email'] for u in results]
        assert 'test@example.com' in emails
        assert 'admin@example.com' in emails

    def test_list_users_pagination(self, admin_client):
        for i in range(25):
            User.objects.create_user(
                username=f'bulkuser{i}',
                email=f'bulk{i}@example.com',
                password='testpass123',
            )
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) <= 20
        assert response.data['count'] >= 25

    def test_list_users_filter_by_is_active(self, admin_client, user):
        user.is_active = False
        user.save()
        response = admin_client.get(self.url, {'is_active': 'false'})
        assert response.status_code == status.HTTP_200_OK
        for u in response.data['results']:
            assert u['is_active'] is False

    def test_list_users_filter_by_is_staff(self, admin_client, admin_user):
        response = admin_client.get(self.url, {'is_staff': 'true'})
        assert response.status_code == status.HTTP_200_OK
        for u in response.data['results']:
            assert u['is_staff'] is True

    def test_list_users_includes_profile(self, admin_client, user):
        response = admin_client.get(self.url)
        for u in response.data['results']:
            if u['email'] == 'test@example.com':
                assert 'profile' in u
                assert u['profile']['subscription_plan'] == 'free'


# ---------------------------------------------------------------------------
# User Detail (Admin only)
# ---------------------------------------------------------------------------

class TestUserDetailView:
    def test_get_user_as_admin(self, admin_client, user):
        response = admin_client.get(f'/api/users/admin/{user.pk}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == 'test@example.com'
        assert 'profile' in response.data

    def test_get_user_deny_regular_user(self, auth_client, user):
        response = auth_client.get(f'/api/users/admin/{user.pk}/')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_user_unauthenticated(self, api_client, user):
        response = api_client.get(f'/api/users/admin/{user.pk}/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_nonexistent_user(self, admin_client):
        import uuid
        response = admin_client.get(f'/api/users/admin/{uuid.uuid4()}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_user_as_admin(self, admin_client, user):
        response = admin_client.patch(
            f'/api/users/admin/{user.pk}/',
            {'first_name': 'AdminUpdated'},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'AdminUpdated'
        user.refresh_from_db()
        assert user.first_name == 'AdminUpdated'


# ---------------------------------------------------------------------------
# Admin Dashboard Stats
# ---------------------------------------------------------------------------

class TestAdminDashboardStats:
    url = '/api/users/admin/dashboard/stats/'

    def test_stats_as_admin(self, admin_client, user):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'user_statistics' in response.data
        assert 'bot_statistics' in response.data
        assert 'trading_statistics' in response.data
        assert 'financial_statistics' in response.data

    def test_stats_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_stats_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_stats_user_counts(self, admin_client, user):
        response = admin_client.get(self.url)
        stats = response.data['user_statistics']
        assert stats['total_users'] >= 2
        assert 'subscription_distribution' in stats


# ---------------------------------------------------------------------------
# Admin Bots Overview
# ---------------------------------------------------------------------------

class TestAdminBotsOverview:
    url = '/api/users/admin/bots/overview/'

    def test_bots_overview_as_admin(self, admin_client):
        response = admin_client.get(self.url)
        if response.status_code != 200:
            print(f'\nERROR RESPONSE: {response.data}')
        assert response.status_code == status.HTTP_200_OK
        assert 'total_bots' in response.data
        assert 'running_bots' in response.data
        assert 'by_type' in response.data
        assert 'by_exchange' in response.data

    def test_bots_overview_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_bots_overview_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Admin Create Blockchain Address
# ---------------------------------------------------------------------------

class TestAdminCreateBlockchainAddress:
    url = '/api/users/admin/blockchain-addresses/'

    def test_create_address_as_admin(self, admin_client):
        data = {
            'coin_type': 'USDT',
            'blockchain': 'BEP20',
            'address': '0x1234567890abcdef1234567890abcdef12345678',
        }
        response = admin_client.post(self.url, data, format='json')
        if response.status_code != 201:
            print(f'\nERROR RESPONSE: {response.data}')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['address']['coin_type'] == 'USDT'
        assert response.data['address']['blockchain'] == 'BEP20'

    def test_create_address_missing_fields(self, admin_client):
        response = admin_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_address_deny_regular_user(self, auth_client):
        response = auth_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_address_deny_unauthenticated(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Admin Trade Logs
# ---------------------------------------------------------------------------

class TestAdminTradeLogs:
    url = '/api/users/admin/trade-logs/'

    def test_trade_logs_as_admin(self, admin_client):
        response = admin_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_trade_logs_deny_regular_user(self, auth_client):
        response = auth_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_trade_logs_deny_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Admin Restrict User
# ---------------------------------------------------------------------------

class TestAdminRestrictUser:
    def test_disable_user(self, admin_client, user):
        response = admin_client.post(
            f'/api/users/admin/users/{user.pk}/restrict/',
            {'action': 'disable'},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is False
        user.refresh_from_db()
        assert user.is_active is False

    def test_enable_user(self, admin_client, user):
        user.is_active = False
        user.save()
        response = admin_client.post(
            f'/api/users/admin/users/{user.pk}/restrict/',
            {'action': 'enable'},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is True
        user.refresh_from_db()
        assert user.is_active is True

    def test_restrict_user_nonexistent(self, admin_client):
        import uuid
        response = admin_client.post(
            f'/api/users/admin/users/{uuid.uuid4()}/restrict/',
            {'action': 'disable'},
            format='json'
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_restrict_user_invalid_action(self, admin_client, user):
        response = admin_client.post(
            f'/api/users/admin/users/{user.pk}/restrict/',
            {'action': 'invalid'},
            format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_restrict_user_deny_regular_user(self, auth_client, user):
        response = auth_client.post(
            f'/api/users/admin/users/{user.pk}/restrict/',
            {'action': 'disable'},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_restrict_user_unauthenticated(self, api_client, user):
        response = api_client.post(
            f'/api/users/admin/users/{user.pk}/restrict/',
            {'action': 'disable'},
            format='json'
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Admin Send Email
# ---------------------------------------------------------------------------

class TestAdminSendEmail:
    url = '/api/users/admin/emails/send/'

    def test_send_email_as_admin(self, admin_client, user):
        data = {
            'subject': 'Test Subject',
            'message': 'Test message body',
            'recipients': [str(user.pk)],
        }
        response = admin_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_send_email_missing_fields(self, admin_client):
        response = admin_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_send_email_deny_regular_user(self, auth_client):
        response = auth_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_send_email_deny_unauthenticated(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_send_email_to_all(self, admin_client, user):
        data = {
            'subject': 'System Update',
            'message': 'Important update',
            'recipients': 'all',
        }
        response = admin_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_send_email_invalid_type(self, admin_client):
        data = {
            'type': 'invalid',
            'subject': 'Test',
            'message': 'Test',
            'recipients': 'all',
        }
        response = admin_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Admin Process Withdrawals
# ---------------------------------------------------------------------------

class TestAdminProcessWithdrawals:
    url = '/api/users/admin/withdrawals/process/'

    def test_process_withdrawals_as_admin(self, admin_client):
        response = admin_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_process_withdrawals_deny_regular_user(self, auth_client):
        response = auth_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_process_withdrawals_deny_unauthenticated(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# User Model Registration via Admin
# ---------------------------------------------------------------------------

class TestUserModelRegistration:
    def test_user_creation_via_admin(self, admin_client):
        data = {
            'username': 'regtest',
            'email': 'regtest@example.com',
            'password': 'StrongPass123!',
        }
        from django.urls import reverse
        from apps.authentication.serializers import UserRegistrationSerializer
        url = '/api/auth/register/'
        client = APIClient()
        response = client.post(url, {
            **data,
            'password_confirm': 'StrongPass123!',
        }, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email='regtest@example.com').exists()

    def test_superuser_has_staff_access(self, api_client, admin_user):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get('/api/users/admin/')
        assert response.status_code == status.HTTP_200_OK
