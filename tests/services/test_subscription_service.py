from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.subscription_service import SubscriptionService

pytestmark = pytest.mark.django_db


class TestApproveSubscription:
    @pytest.fixture(autouse=True)
    def _patch_g5_referral_hook(self):
        """G5 hook calls ReferralRewardService.record_subscription_payment
        which crashes on MagicMock subscriptions (amount_due is a MagicMock).
        These are unit tests for approve_subscription — patch the hook out."""
        with patch(
            "services.referral_rewards.ReferralRewardService.record_subscription_payment",
            return_value=None,
        ):
            yield

    def test_approve_pending_payment_success(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "custom"
        mock_sub.user.email = "test@example.com"
        mock_sub.id = "sub-123"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create") as mock_audit:
                result = SubscriptionService.approve_subscription("sub-123", "admin", "notes")

                mock_sub.approve.assert_called_once_with("admin", "notes")
                mock_audit.assert_called_once()
                assert mock_audit.call_args[1]["action"] == "bot_subscription_approved"
                assert result == mock_sub

    def test_approve_pending_approval_success(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_approval"
        mock_sub.plan.bot_type = "quantum_ai"
        mock_sub.user.email = "test@example.com"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                with patch.object(
                    SubscriptionService, "_create_quantum_ai_investment"
                ) as mock_create:
                    result = SubscriptionService.approve_subscription("sub-123", "admin")
                    mock_create.assert_called_once_with(mock_sub)
                    assert result == mock_sub

    def test_approve_invalid_status(self):
        mock_sub = MagicMock()
        mock_sub.status = "active"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with pytest.raises(ValueError, match="Cannot approve subscription with status: active"):
                SubscriptionService.approve_subscription("sub-123", "admin")

    def test_approve_expired_status_allowed_for_resubscribe(self):
        # G4 / FR A6: re-subscribe restore — an "expired" row MUST be
        # re-approvable (approve() stamps a fresh clock, bots retained).
        mock_sub = MagicMock()
        mock_sub.status = "expired"
        mock_sub.plan.bot_type = "custom"
        mock_sub.user.email = "test@example.com"
        mock_sub.id = "sub-123"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                result = SubscriptionService.approve_subscription("sub-123", "admin")
                mock_sub.approve.assert_called_once_with("admin", "")
                assert result == mock_sub

    def test_approve_cancelled_status(self):
        mock_sub = MagicMock()
        mock_sub.status = "cancelled"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with pytest.raises(ValueError, match="cancelled"):
                SubscriptionService.approve_subscription("sub-123", "admin")

    def test_approve_logs_correctly(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "grid"
        mock_sub.user.email = "user@test.com"
        mock_sub.id = "sub-uuid"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create") as mock_audit:
                SubscriptionService.approve_subscription("sub-uuid", "admin", "approved!")

                call_kwargs = mock_audit.call_args[1]
                assert call_kwargs["user"] == "admin"
                assert call_kwargs["action"] == "bot_subscription_approved"
                assert call_kwargs["resource_type"] == "BotSubscription"
                assert call_kwargs["resource_id"] == "sub-uuid"
                assert "grid" in call_kwargs["description"]

    def test_approve_quantum_ai_calls_create_investment(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "quantum_ai"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                with patch.object(
                    SubscriptionService, "_create_quantum_ai_investment"
                ) as mock_create:
                    SubscriptionService.approve_subscription("sub-123", "admin")
                    mock_create.assert_called_once()

    def test_approve_non_quantum_does_not_call_create(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "grid"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                with patch.object(
                    SubscriptionService, "_create_quantum_ai_investment"
                ) as mock_create:
                    SubscriptionService.approve_subscription("sub-123", "admin")
                    mock_create.assert_not_called()

    def test_approve_raises_on_orm_error(self):
        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.side_effect = Exception("DB error")
            with pytest.raises(Exception, match="DB error"):
                SubscriptionService.approve_subscription("sub-123", "admin")

    def test_approve_uses_select_for_update(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update",
            return_value=mock_qs,
        ):
            mock_sub = MagicMock()
            mock_sub.status = "pending_payment"
            mock_sub.plan.bot_type = "custom"
            mock_sub.user.email = "test@test.com"
            mock_qs.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                SubscriptionService.approve_subscription("sub-123", "admin")
                mock_qs.get.assert_called_once_with(id="sub-123")


class TestRejectSubscription:
    def test_reject_pending_payment_success(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "grid"
        mock_sub.id = "sub-456"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create") as mock_audit:
                result = SubscriptionService.reject_subscription("sub-456", "admin", "bad payment")

                mock_sub.reject.assert_called_once_with("admin", "bad payment")
                mock_audit.assert_called_once()
                assert mock_audit.call_args[1]["action"] == "bot_subscription_rejected"
                assert result == mock_sub

    def test_reject_pending_approval_success(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_approval"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                result = SubscriptionService.reject_subscription("sub-456", "admin", "reason")
                assert result == mock_sub

    def test_reject_invalid_status(self):
        mock_sub = MagicMock()
        mock_sub.status = "active"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with pytest.raises(ValueError, match="Cannot reject subscription with status: active"):
                SubscriptionService.reject_subscription("sub-456", "admin", "reason")

    def test_reject_logs_rejection(self):
        mock_sub = MagicMock()
        mock_sub.status = "pending_payment"
        mock_sub.plan.bot_type = "martingale"

        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create") as mock_audit:
                SubscriptionService.reject_subscription("sub-456", "admin", "fraud detected")

                call_kwargs = mock_audit.call_args[1]
                assert call_kwargs["action"] == "bot_subscription_rejected"
                assert call_kwargs["new_values"] == {"rejection_reason": "fraud detected"}
                assert "fraud detected" in call_kwargs["description"]

    def test_reject_selects_for_update(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.select_for_update",
            return_value=mock_qs,
        ):
            mock_sub = MagicMock()
            mock_sub.status = "pending_payment"
            mock_qs.get.return_value = mock_sub
            with patch("services.subscription_service.AuditLog.objects.create"):
                SubscriptionService.reject_subscription("sub-456", "admin", "no reason")
                mock_qs.get.assert_called_once_with(id="sub-456")


class TestGetPendingSubscriptions:
    def test_filters_pending_approval(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.filter", return_value=mock_qs
        ) as mock_filter:
            mock_qs.select_related.return_value.order_by.return_value = ["sub1", "sub2"]

            result = SubscriptionService.get_pending_subscriptions()

            mock_filter.assert_called_once_with(status="pending_approval")
            assert result == ["sub1", "sub2"]

    def test_uses_select_related_user_plan(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.filter", return_value=mock_qs
        ):
            SubscriptionService.get_pending_subscriptions()
            mock_qs.select_related.assert_called_once_with("user", "plan")

    def test_orders_by_created_at_desc(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.filter", return_value=mock_qs
        ):
            mock_qs.select_related.return_value.order_by.return_value = []
            SubscriptionService.get_pending_subscriptions()
            mock_qs.select_related.return_value.order_by.assert_called_once_with("-created_at")

    def test_empty_result(self):
        mock_qs = MagicMock()
        with patch(
            "services.subscription_service.BotSubscription.objects.filter", return_value=mock_qs
        ):
            mock_qs.select_related.return_value.order_by.return_value = []
            result = SubscriptionService.get_pending_subscriptions()
            assert result == []


class TestGetDashboardStats:
    def test_aggregates_correctly(self):
        mock_stats = {
            "total": 100,
            "pending_approval": 10,
            "active": 50,
            "expired": 20,
            "total_revenue": Decimal("5000.00"),
        }
        with patch(
            "services.subscription_service.BotSubscription.objects.aggregate",
            return_value=mock_stats,
        ):
            result = SubscriptionService.get_subscription_dashboard_stats()
            assert result["total"] == 100
            assert result["pending_approval"] == 10
            assert result["active"] == 50
            assert result["expired"] == 20
            assert result["total_revenue"] == Decimal("5000.00")

    def test_zero_stats(self):
        mock_stats = {
            "total": 0,
            "pending_approval": 0,
            "active": 0,
            "expired": 0,
            "total_revenue": Decimal("0"),
        }
        with patch(
            "services.subscription_service.BotSubscription.objects.aggregate",
            return_value=mock_stats,
        ):
            result = SubscriptionService.get_subscription_dashboard_stats()
            assert result["total"] == 0
            assert result["total_revenue"] == Decimal("0")


class TestCreateInvestorPortfolio:
    def test_creates_investment_with_active_fund(self):
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_sub = MagicMock()
        mock_sub.user = mock_user

        mock_fund = MagicMock()
        mock_fund.total_deposits = Decimal("1000")
        mock_fund.default_lock_days = 30

        with patch("services.subscription_service.QuantumAIFund.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_fund
            with patch(
                "services.subscription_service.InvestorPortfolio.objects.create"
            ) as mock_create:
                with patch("services.quantum_locks.QuantumLockService.create_lock") as mock_lock:
                    mock_investment = MagicMock()
                    mock_investment.amount = Decimal("100")
                    mock_investment.calculate_share_percentage.return_value = Decimal("10.0")
                    mock_create.return_value = mock_investment

                    SubscriptionService._create_quantum_ai_investment(mock_sub)

                    mock_filter.assert_called_once_with(is_active=True)
                    mock_create.assert_called_once()
                    args, kwargs = mock_create.call_args
                    assert kwargs["user"] == mock_user
                    assert kwargs["fund"] == mock_fund
                    assert kwargs["subscription"] == mock_sub
                    assert kwargs["status"] == "pending"
                    mock_investment.calculate_share_percentage.assert_called_once()
                    mock_investment.save.assert_called_once()
                    # A5: investment creation also opens the investor lock
                    mock_lock.assert_called_once()
                    lock_kwargs = mock_lock.call_args[1]
                    assert lock_kwargs["user"] == mock_user
                    assert lock_kwargs["fund"] == mock_fund
                    assert lock_kwargs["subscription"] == mock_sub
                    assert lock_kwargs["lock_days"] == 30

    def test_no_active_fund_raises_error(self):
        mock_sub = MagicMock()

        with patch("services.subscription_service.QuantumAIFund.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = None
            with pytest.raises(ValueError, match="No active Quantum AI fund found"):
                SubscriptionService._create_quantum_ai_investment(mock_sub)

    def test_investment_created_with_pending_status(self):
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        mock_sub = MagicMock()
        mock_sub.user = mock_user
        mock_fund = MagicMock()
        mock_fund.total_deposits = Decimal("1000")
        mock_fund.default_lock_days = 30

        with patch("services.subscription_service.QuantumAIFund.objects.filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_fund
            with patch(
                "services.subscription_service.InvestorPortfolio.objects.create"
            ) as mock_create:
                with patch("services.quantum_locks.QuantumLockService.create_lock") as mock_lock:
                    mock_investment = MagicMock()
                    mock_investment.calculate_share_percentage.return_value = Decimal("5.0")
                    mock_create.return_value = mock_investment

                    SubscriptionService._create_quantum_ai_investment(mock_sub)

                    assert mock_create.call_args[1]["status"] == "pending"
                    mock_lock.assert_called_once()
