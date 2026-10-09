import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from core.models import (
    AuditLog,
    SoftDeleteModel,
    SystemConfiguration,
    TimeStampedModel,
    UserActivityLog,
)

User = get_user_model()


@pytest.mark.django_db
class TestTimeStampedModel:
    def test_time_stamped_model_is_abstract(self):
        assert TimeStampedModel._meta.abstract is True

    def test_auto_timestamps_on_concrete_model(self):
        class ConcreteModel(TimeStampedModel):
            name = models.CharField(max_length=50)

            class Meta:
                app_label = "core"

        assert ConcreteModel._meta.abstract is False
        fields = {f.name: f for f in ConcreteModel._meta.fields}
        assert "id" in fields
        assert "created_at" in fields
        assert "updated_at" in fields

    def test_uuid_primary_key(self):
        model = UserActivityLog(
            user=User.objects.create(username="u1", email="u1@test.com", password="pass"),
            action="test",
        )
        assert isinstance(model.id, uuid.UUID)
        assert model.pk is not None


@pytest.mark.django_db
class TestSoftDeleteModel:
    def test_soft_delete_model_is_abstract(self):
        assert SoftDeleteModel._meta.abstract is True

    def test_soft_delete_sets_flags(self):
        user = User.objects.create(username="test_sd", email="sd@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="delete_me")
        assert log.is_deleted is False
        assert log.deleted_at is None

        log.delete()
        log.refresh_from_db()
        assert log.is_deleted is True
        assert log.deleted_at is not None

    def test_soft_delete_sets_timestamp(self):
        user = User.objects.create(username="ts_sd", email="ts@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="time_check")
        before = timezone.now()
        log.delete()
        log.refresh_from_db()
        assert before <= log.deleted_at <= timezone.now()

    def test_restore_after_soft_delete(self):
        user = User.objects.create(username="restore", email="restore@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="to_restore")
        log.delete()
        log.refresh_from_db()
        assert log.is_deleted is True

        log.restore()
        log.refresh_from_db()
        assert log.is_deleted is False
        assert log.deleted_at is None

    def test_restore_on_non_deleted(self):
        user = User.objects.create(username="non_del", email="nd@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="never_deleted")
        log.restore()
        log.refresh_from_db()
        assert log.is_deleted is False
        assert log.deleted_at is None

    def test_hard_delete_removes_record(self):
        user = User.objects.create(username="hard_del", email="hd@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="hard_delete_me")
        pk = log.pk
        log.hard_delete()
        assert not UserActivityLog.objects.filter(pk=pk).exists()

    def test_multiple_soft_deletes(self):
        user = User.objects.create(username="multi", email="multi@test.com", password="pass")
        log = UserActivityLog.objects.create(user=user, action="multi_delete")
        log.delete()
        log.refresh_from_db()
        t1 = log.deleted_at
        log.restore()
        log.delete()
        log.refresh_from_db()
        t2 = log.deleted_at
        assert t2 > t1

    def test_bulk_objects_not_affected(self):
        user = User.objects.create(username="bulk", email="bulk@test.com", password="pass")
        log1 = UserActivityLog.objects.create(user=user, action="deletable")
        log2 = UserActivityLog.objects.create(user=user, action="keep")
        log1.delete()
        # FIN-2: Default manager now filters out soft-deleted records.
        # Use all_with_deleted() to see both active and deleted.
        logs = UserActivityLog.objects.all_with_deleted().filter(user=user)
        assert logs.count() == 2
        log1.refresh_from_db()
        assert log1.is_deleted is True
        log2.refresh_from_db()
        assert log2.is_deleted is False
        # Default manager only shows active
        active_logs = UserActivityLog.objects.filter(user=user)
        assert active_logs.count() == 1


@pytest.mark.django_db
class TestUserActivityLog:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            username="activity_user",
            email="activity@test.com",
            password="pass",
        )

    def test_create_activity_log(self, user):
        log = UserActivityLog.objects.create(
            user=user,
            action="login",
            description="User logged in",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            endpoint="/api/auth/login/",
            method="POST",
            status_code=200,
        )
        assert log.pk is not None
        assert log.user == user
        assert log.action == "login"
        assert log.description == "User logged in"
        assert log.ip_address == "192.168.1.1"
        assert log.user_agent == "Mozilla/5.0"
        assert log.endpoint == "/api/auth/login/"
        assert log.method == "POST"
        assert log.status_code == 200

    def test_auto_timestamps(self, user):
        log = UserActivityLog.objects.create(user=user, action="test")
        assert log.created_at is not None
        assert log.updated_at is not None

    def test_string_representation(self, user):
        log = UserActivityLog.objects.create(user=user, action="test_action")
        assert str(log) == f"{user.email} - test_action at {log.created_at}"

    def test_default_values(self, user):
        log = UserActivityLog.objects.create(user=user, action="defaults")
        assert log.description == ""
        assert log.ip_address is None
        assert log.user_agent == ""
        assert log.endpoint == ""
        assert log.method == ""
        assert log.status_code is None

    def test_db_table(self):
        assert UserActivityLog._meta.db_table == "core_user_activity_log"

    def test_indexes(self):
        indexes = {tuple(idx.fields): idx for idx in UserActivityLog._meta.indexes}
        assert ("user", "created_at") in indexes
        assert ("action", "created_at") in indexes

    def test_cascade_delete(self, user):
        log = UserActivityLog.objects.create(user=user, action="test")
        user.delete()
        assert UserActivityLog.objects.filter(pk=log.pk).count() == 0


@pytest.mark.django_db
class TestSystemConfiguration:
    def test_create_config(self):
        config = SystemConfiguration.objects.create(
            key="MAX_TRADE_AMOUNT",
            value="50000",
            description="Maximum trade amount in USDT",
        )
        assert config.pk is not None
        assert config.key == "MAX_TRADE_AMOUNT"
        assert config.value == "50000"
        assert config.description == "Maximum trade amount in USDT"
        assert config.is_active is True

    def test_unique_key(self):
        SystemConfiguration.objects.create(key="UNIQUE_KEY", value="1")
        with pytest.raises(Exception):
            SystemConfiguration.objects.create(key="UNIQUE_KEY", value="2")

    def test_string_representation(self):
        config = SystemConfiguration.objects.create(key="TEST_KEY", value="test_value")
        assert str(config) == "TEST_KEY = test_value"

    def test_default_is_active(self):
        config = SystemConfiguration.objects.create(key="ACTIVE_DEFAULT", value="true")
        assert config.is_active is True

    def test_inactive_config(self):
        config = SystemConfiguration.objects.create(key="INACTIVE", value="false", is_active=False)
        assert config.is_active is False
        config.is_active = True
        config.save()
        config.refresh_from_db()
        assert config.is_active is True

    def test_db_table(self):
        assert SystemConfiguration._meta.db_table == "core_system_configuration"

    def test_auto_timestamps(self):
        config = SystemConfiguration.objects.create(key="TIMESTAMPS", value="check")
        assert config.created_at is not None
        assert config.updated_at is not None


@pytest.mark.django_db
class TestAuditLog:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            username="audit_user",
            email="audit@test.com",
            password="pass",
        )

    def test_create_audit_log(self, user):
        log = AuditLog.objects.create(
            user=user,
            action="create",
            resource_type="Bot",
            resource_id="123",
            old_values=None,
            new_values={"name": "Test Bot"},
            description="Created new bot",
            ip_address="10.0.0.1",
            user_agent="curl/7.68",
        )
        assert log.pk is not None
        assert log.user == user
        assert log.action == "create"
        assert log.resource_type == "Bot"
        assert log.resource_id == "123"
        assert log.old_values is None
        assert log.new_values == {"name": "Test Bot"}
        assert log.description == "Created new bot"
        assert log.ip_address == "10.0.0.1"
        assert log.user_agent == "curl/7.68"

    def test_audit_log_without_user(self):
        log = AuditLog.objects.create(
            action="login",
            resource_type="User",
            description="Anonymous login attempt",
        )
        assert log.user is None

    def test_all_action_choices(self, user):
        for action, _ in AuditLog.ACTION_CHOICES:
            log = AuditLog.objects.create(
                user=user, action=action, resource_type="Test", description=action
            )
            assert log.action == action

    def test_string_representation(self, user):
        log = AuditLog.objects.create(
            user=user, action="update", resource_type="Config", description="Updated config"
        )
        assert str(log) == f"update on Config at {log.created_at}"

    def test_old_new_values_json(self, user):
        old = {"key": "old_value"}
        new = {"key": "new_value"}
        log = AuditLog.objects.create(
            user=user,
            action="update",
            resource_type="Config",
            old_values=old,
            new_values=new,
            description="Changed config key",
        )
        log.refresh_from_db()
        assert log.old_values == old
        assert log.new_values == new

    def test_default_blank_values(self, user):
        log = AuditLog.objects.create(
            user=user, action="create", resource_type="Test", description="test"
        )
        assert log.resource_id == ""
        assert log.old_values is None
        assert log.new_values is None
        assert log.ip_address is None
        assert log.user_agent == ""

    def test_db_table(self):
        assert AuditLog._meta.db_table == "core_audit_log"

    def test_indexes(self):
        indexes = {tuple(idx.fields): idx for idx in AuditLog._meta.indexes}
        assert ("user", "created_at") in indexes
        assert ("action", "created_at") in indexes
        assert ("resource_type", "resource_id") in indexes

    def test_on_delete_set_null(self, user):
        log = AuditLog.objects.create(
            user=user, action="delete", resource_type="Test", description="user deleted"
        )
        user.delete()
        log.refresh_from_db()
        assert log.user is None

    def test_auto_timestamps(self, user):
        log = AuditLog.objects.create(
            user=user, action="create", resource_type="Test", description="time check"
        )
        assert log.created_at is not None
        assert log.updated_at is not None
