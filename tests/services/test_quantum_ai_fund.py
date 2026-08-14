from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.bots.models import QuantumAIFund, QuantumAIInvestment, ReserveFund
from services.quantum_ai_fund import QuantumAIFundService

pytestmark = pytest.mark.django_db


class TestSmoothingModel:
    """Tests for QuantumAIFund.calculate_smoothed_return / calculate_excess_return"""

    def _make_fund(self, min_r=Decimal("2"), max_r=Decimal("15")):
        fund = MagicMock(spec=QuantumAIFund)
        fund.monthly_min_return = min_r
        fund.monthly_max_return = max_r

        def smoothed(actual):
            return max(fund.monthly_min_return, min(actual, fund.monthly_max_return))

        fund.calculate_smoothed_return = smoothed
        return fund

    def test_smoothed_return_below_min_returns_min(self):
        fund = self._make_fund()
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("-5")) == Decimal("2")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("0")) == Decimal("2")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("1")) == Decimal("2")

    def test_smoothed_return_within_range_passthrough(self):
        fund = self._make_fund()
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("5")) == Decimal("5")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("10")) == Decimal("10")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("2")) == Decimal("2")

    def test_smoothed_return_above_max_caps(self):
        fund = self._make_fund()
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("20")) == Decimal("15")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("50")) == Decimal("15")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("15")) == Decimal("15")

    def test_excess_negative_when_actual_below_min(self):
        fund = self._make_fund()
        result = QuantumAIFund.calculate_excess_return(fund, Decimal("-5"))
        assert result == Decimal("-7")  # -5 - 2 = -7
        assert QuantumAIFund.calculate_excess_return(fund, Decimal("0")) == Decimal("-2")

    def test_excess_zero_when_within_range(self):
        fund = self._make_fund()
        assert QuantumAIFund.calculate_excess_return(fund, Decimal("5")) == Decimal("0")
        assert QuantumAIFund.calculate_excess_return(fund, Decimal("10")) == Decimal("0")

    def test_excess_positive_when_above_max(self):
        fund = self._make_fund()
        assert QuantumAIFund.calculate_excess_return(fund, Decimal("20")) == Decimal("5")
        assert QuantumAIFund.calculate_excess_return(fund, Decimal("30")) == Decimal("15")

    def test_min_equals_max_no_range(self):
        fund = self._make_fund(min_r=Decimal("10"), max_r=Decimal("10"))
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("0")) == Decimal("10")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("20")) == Decimal("10")

    def test_zero_min(self):
        fund = self._make_fund(min_r=Decimal("0"))
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("-10")) == Decimal("0")
        assert QuantumAIFund.calculate_smoothed_return(fund, Decimal("5")) == Decimal("5")


class TestReserveFundModel:
    def _make_reserve(
        self, balance=Decimal("0"), deposits=Decimal("10000"), buffer_pct=Decimal("10")
    ):
        fund = MagicMock(spec=QuantumAIFund)
        fund.total_deposits = deposits
        fund.reserve_buffer_pct = buffer_pct
        reserve = MagicMock(spec=ReserveFund)
        reserve.fund = fund
        reserve.balance = balance
        return reserve

    def test_is_below_target_when_below(self):
        reserve = self._make_reserve(balance=Decimal("500"))
        assert ReserveFund.is_below_target(reserve) is True

    def test_is_below_target_when_at_target(self):
        reserve = self._make_reserve(balance=Decimal("1000"))
        assert ReserveFund.is_below_target(reserve) is False

    def test_is_below_target_when_above(self):
        reserve = self._make_reserve(balance=Decimal("2000"))
        assert ReserveFund.is_below_target(reserve) is False

    def test_is_below_target_zero_deposits(self):
        reserve = self._make_reserve(balance=Decimal("0"), deposits=Decimal("0"))
        assert ReserveFund.is_below_target(reserve) is True

    def test_can_cover_true(self):
        reserve = self._make_reserve(balance=Decimal("1000"))
        assert ReserveFund.can_cover(reserve, Decimal("500")) is True
        assert ReserveFund.can_cover(reserve, Decimal("1000")) is True

    def test_can_cover_false(self):
        reserve = self._make_reserve(balance=Decimal("500"))
        assert ReserveFund.can_cover(reserve, Decimal("1000")) is False


class TestUpdateFundPerformanceSmoothed:
    def test_update_success_within_range_passthrough(self):
        """10% actual return within 2-15% range: shown = 10%, no reserve activity."""
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("10000")
        mock_fund.total_deposits = Decimal("8000")
        mock_fund.monthly_min_return = Decimal("2")
        mock_fund.monthly_max_return = Decimal("15")
        mock_fund.calculate_smoothed_return.return_value = Decimal("10")
        mock_fund.calculate_excess_return.return_value = Decimal("0")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit") as mock_accrue:
                with patch.object(QuantumAIFundService, "_apply_reserve_cover") as mock_cover:
                    with patch.object(
                        QuantumAIFundService, "_deposit_excess_to_reserve"
                    ) as mock_deposit:
                        QuantumAIFundService.update_fund_performance("fund-1", Decimal("11000"))

                        mock_accrue.assert_called_once_with("fund-1", Decimal("10"))
                        mock_cover.assert_not_called()
                        mock_deposit.assert_not_called()

    def test_update_below_min_triggers_reserve_cover(self):
        """-5% actual return, min=2%: shown=2%, reserve covers 7% gap."""
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("10000")
        mock_fund.total_deposits = Decimal("8000")
        mock_fund.monthly_min_return = Decimal("2")
        mock_fund.monthly_max_return = Decimal("15")
        mock_fund.calculate_smoothed_return.return_value = Decimal("2")
        mock_fund.calculate_excess_return.return_value = Decimal("-7")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit") as mock_accrue:
                with patch.object(QuantumAIFundService, "_apply_reserve_cover") as mock_cover:
                    with patch.object(
                        QuantumAIFundService, "_deposit_excess_to_reserve"
                    ) as mock_deposit:
                        QuantumAIFundService.update_fund_performance("fund-1", Decimal("9500"))

                        mock_accrue.assert_called_once()
                        mock_cover.assert_called_once()
                        cover_amount = mock_cover.call_args[0][1]
                        assert cover_amount > 0
                        mock_deposit.assert_not_called()

    def test_update_above_max_deposits_excess_to_reserve(self):
        """30% actual return, max=15%: shown=15%, 15% excess goes to reserve."""
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("10000")
        mock_fund.total_deposits = Decimal("8000")
        mock_fund.monthly_min_return = Decimal("2")
        mock_fund.monthly_max_return = Decimal("15")
        mock_fund.calculate_smoothed_return.return_value = Decimal("15")
        mock_fund.calculate_excess_return.return_value = Decimal("15")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit") as mock_accrue:
                with patch.object(QuantumAIFundService, "_apply_reserve_cover") as mock_cover:
                    with patch.object(
                        QuantumAIFundService, "_deposit_excess_to_reserve"
                    ) as mock_deposit:
                        QuantumAIFundService.update_fund_performance("fund-1", Decimal("13000"))

                        mock_accrue.assert_called_once()
                        mock_deposit.assert_called_once()
                        deposit_amount = mock_deposit.call_args[0][1]
                        assert deposit_amount > 0
                        mock_cover.assert_not_called()

    def test_update_first_time_no_old_value(self):
        """When old_total_value is 0, skip return calc (first update)."""
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("0")
        mock_fund.total_deposits = Decimal("8000")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit") as mock_accrue:
                with patch.object(QuantumAIFundService, "_apply_reserve_cover"):
                    with patch.object(QuantumAIFundService, "_deposit_excess_to_reserve"):
                        QuantumAIFundService.update_fund_performance("fund-1", Decimal("8000"))
                        mock_accrue.assert_not_called()  # No prior value to compare

    def test_update_sets_total_profit_and_last_trade(self):
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("5000")
        mock_fund.total_deposits = Decimal("5000")
        mock_fund.monthly_min_return = Decimal("2")
        mock_fund.monthly_max_return = Decimal("15")
        mock_fund.calculate_smoothed_return.return_value = Decimal("10")
        mock_fund.calculate_excess_return.return_value = Decimal("0")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit"):
                QuantumAIFundService.update_fund_performance("fund-1", Decimal("6000"))

                assert mock_fund.total_fund_value == Decimal("6000")
                assert mock_fund.total_profit == Decimal("1000")
                assert mock_fund.last_trade_at is not None
                mock_fund.save.assert_called_once()

    def test_update_with_loss_sets_negative_profit(self):
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_fund_value = Decimal("10000")
        mock_fund.total_deposits = Decimal("10000")
        mock_fund.monthly_min_return = Decimal("2")
        mock_fund.monthly_max_return = Decimal("15")
        mock_fund.calculate_smoothed_return.return_value = Decimal("2")
        mock_fund.calculate_excess_return.return_value = Decimal("-7")

        with patch("services.quantum_ai_fund.QuantumAIFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_fund
            with patch.object(QuantumAIFundService, "_accrue_smoothed_profit"):
                with patch.object(QuantumAIFundService, "_apply_reserve_cover"):
                    with patch.object(QuantumAIFundService, "_deposit_excess_to_reserve"):
                        QuantumAIFundService.update_fund_performance("fund-1", Decimal("8000"))
                        assert mock_fund.total_profit == Decimal("-2000")


class TestApplyReserveCover:
    def test_cover_sufficient_balance(self):
        mock_reserve = MagicMock(spec=ReserveFund)
        mock_reserve.balance = Decimal("1000")
        mock_reserve.can_cover.return_value = True

        with patch("services.quantum_ai_fund.ReserveFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_reserve
            QuantumAIFundService._apply_reserve_cover("fund-1", Decimal("300"))
            assert mock_reserve.balance == Decimal("700")
            assert mock_reserve.last_withdrawal is not None
            mock_reserve.save.assert_called_once()

    def test_cover_insufficient_sets_alert(self):
        mock_reserve = MagicMock(spec=ReserveFund)
        mock_reserve.balance = Decimal("100")
        mock_reserve.can_cover.return_value = False

        with patch("services.quantum_ai_fund.ReserveFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.return_value = mock_reserve
            QuantumAIFundService._apply_reserve_cover("fund-1", Decimal("500"))
            assert mock_reserve.balance == Decimal("0")
            assert mock_reserve.low_balance_alert_sent is True

    def test_cover_no_reserve_fund_exists(self):
        with patch("services.quantum_ai_fund.ReserveFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get.side_effect = ReserveFund.DoesNotExist
            # Should not raise, just log error
            QuantumAIFundService._apply_reserve_cover("fund-1", Decimal("100"))


class TestDepositExcessToReserve:
    def test_deposit_to_existing_reserve(self):
        mock_reserve = MagicMock(spec=ReserveFund)
        mock_reserve.balance = Decimal("500")

        with patch("services.quantum_ai_fund.ReserveFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get_or_create.return_value = (mock_reserve, False)
            QuantumAIFundService._deposit_excess_to_reserve("fund-1", Decimal("300"))
            assert mock_reserve.balance == Decimal("800")
            assert mock_reserve.low_balance_alert_sent is False
            mock_reserve.save.assert_called_once()

    def test_deposit_creates_new_reserve(self):
        mock_reserve = MagicMock(spec=ReserveFund)
        mock_reserve.balance = Decimal("0")

        with patch("services.quantum_ai_fund.ReserveFund.objects.select_for_update") as mock_sfu:
            mock_sfu.return_value.get_or_create.return_value = (mock_reserve, True)
            QuantumAIFundService._deposit_excess_to_reserve("fund-1", Decimal("1000"))
            assert mock_reserve.balance == Decimal("1000")


class TestAccrueSmoothedProfit:

    def test_accrue_to_multiple_investors(self):
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_deposits = Decimal("10000")

        inv1 = MagicMock(spec=QuantumAIInvestment)
        inv1.amount = Decimal("3000")  # 30% share
        inv1.accrued_profit = Decimal("0")

        inv2 = MagicMock(spec=QuantumAIInvestment)
        inv2.amount = Decimal("7000")  # 70% share
        inv2.accrued_profit = Decimal("0")

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        mock_qs.__iter__.return_value = iter([inv1, inv2])
        mock_qs.count.return_value = 2
        mock_qs.select_for_update.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs

        mock_mgr = MagicMock()
        mock_mgr.select_for_update.return_value.get.return_value = mock_fund

        with patch("services.quantum_ai_fund.QuantumAIFund.objects", mock_mgr):
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
            ):
                QuantumAIFundService._accrue_smoothed_profit("fund-1", Decimal("10"))

                # 10% of 10000 = 1000 total shown value
                # inv1: 3000/10000 * 1000 = 300
                # inv2: 7000/10000 * 1000 = 700
                assert inv1.accrued_profit == Decimal("300")
                assert inv2.accrued_profit == Decimal("700")
                inv1.save.assert_called_once()
                inv2.save.assert_called_once()

    def test_accrue_no_investors_skips(self):
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_deposits = Decimal("10000")

        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        mock_qs.__iter__.return_value = iter([])
        mock_qs.select_for_update.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs

        mock_mgr = MagicMock()
        mock_mgr.select_for_update.return_value.get.return_value = mock_fund

        with patch("services.quantum_ai_fund.QuantumAIFund.objects", mock_mgr):
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
            ):
                # Should not raise
                QuantumAIFundService._accrue_smoothed_profit("fund-1", Decimal("10"))

    def test_accrue_zero_deposits(self):
        mock_fund = MagicMock(spec=QuantumAIFund)
        mock_fund.id = "fund-1"
        mock_fund.total_deposits = Decimal("0")

        inv = MagicMock(spec=QuantumAIInvestment)
        inv.amount = Decimal("1000")

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        mock_qs.__iter__.return_value = iter([inv])
        mock_qs.select_for_update.return_value = mock_qs
        mock_qs.select_related.return_value = mock_qs

        mock_mgr = MagicMock()
        mock_mgr.select_for_update.return_value.get.return_value = mock_fund

        with patch("services.quantum_ai_fund.QuantumAIFund.objects", mock_mgr):
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
            ):
                QuantumAIFundService._accrue_smoothed_profit("fund-1", Decimal("10"))
                # Zero deposit means no value to distribute — no save called
                inv.save.assert_not_called()


class TestProcessPayouts:
    def test_process_payouts_success(self):
        mock_fund = MagicMock()
        mock_fund.id = "fund-1"

        inv1 = MagicMock(spec=QuantumAIInvestment)
        inv1.accrued_profit = Decimal("500")
        inv1.total_payouts = Decimal("0")
        inv1.user.email = "user1@test.com"
        inv1.user.id = 1

        inv2 = MagicMock(spec=QuantumAIInvestment)
        inv2.accrued_profit = Decimal("300")
        inv2.total_payouts = Decimal("0")
        inv2.user.email = "user2@test.com"
        inv2.user.id = 2

        mock_inv_qs = MagicMock()
        mock_inv_qs.__iter__.return_value = iter([inv1, inv2])

        with patch(
            "services.quantum_ai_fund.QuantumAIFund.objects.select_for_update"
        ) as mock_fund_sfu:
            mock_fund_sfu.return_value.get.return_value = mock_fund
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter"
            ) as mock_inv_filter:
                mock_inv_filter.return_value.select_for_update.return_value = mock_inv_qs
                with patch(
                    "services.quantum_ai_fund.UserBalance.objects.get_or_create"
                ) as mock_bal:
                    mock_bal.return_value = (MagicMock(available=Decimal("0")), True)
                    with patch("services.quantum_ai_fund.PaymentTransaction.objects.create"):
                        result = QuantumAIFundService.process_payouts("fund-1")

                        assert result["payout_count"] == 2
                        assert result["total_paid"] == Decimal("800")
                        assert inv1.accrued_profit == Decimal("0")
                        assert inv1.total_payouts == Decimal("500")

    def test_payout_handles_partial_failure(self):
        mock_fund = MagicMock()
        mock_fund.id = "fund-1"

        inv_good = MagicMock(spec=QuantumAIInvestment)
        inv_good.accrued_profit = Decimal("100")
        inv_good.total_payouts = Decimal("0")
        inv_good.user.email = "good@test.com"
        inv_good.user.id = 1

        inv_bad = MagicMock(spec=QuantumAIInvestment)
        inv_bad.accrued_profit = Decimal("200")
        inv_bad.total_payouts = Decimal("0")
        inv_bad.user.email = "bad@test.com"
        inv_bad.user.id = 2

        mock_inv_qs = MagicMock()
        mock_inv_qs.__iter__.return_value = iter([inv_good, inv_bad])

        def side_effect(**kwargs):
            if kwargs.get("user") == inv_bad.user:
                raise Exception("Balance creation failed")
            return (MagicMock(available=Decimal("0")), True)

        with patch(
            "services.quantum_ai_fund.QuantumAIFund.objects.select_for_update"
        ) as mock_fund_sfu:
            mock_fund_sfu.return_value.get.return_value = mock_fund
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter"
            ) as mock_inv_filter:
                mock_inv_filter.return_value.select_for_update.return_value = mock_inv_qs
                with patch(
                    "services.quantum_ai_fund.UserBalance.objects.get_or_create",
                    side_effect=side_effect,
                ):
                    with patch("services.quantum_ai_fund.PaymentTransaction.objects.create"):
                        result = QuantumAIFundService.process_payouts("fund-1")

                        assert result["payout_count"] == 1
                        assert result["total_paid"] == Decimal("100")
                        # Bad investment rolled back
                        inv_bad.accrued_profit = Decimal("200")
                        inv_bad.total_payouts = Decimal("0")

    def test_payout_no_investments(self):
        mock_fund = MagicMock()
        mock_fund.id = "fund-1"

        with patch(
            "services.quantum_ai_fund.QuantumAIFund.objects.select_for_update"
        ) as mock_fund_sfu:
            mock_fund_sfu.return_value.get.return_value = mock_fund
            with patch(
                "services.quantum_ai_fund.QuantumAIInvestment.objects.filter"
            ) as mock_inv_filter:
                mock_inv_filter.return_value.select_for_update.return_value = []
                result = QuantumAIFundService.process_payouts("fund-1")
                assert result["payout_count"] == 0
                assert result["total_paid"] == Decimal("0")


class TestGetUserDashboard:
    def test_dashboard_smoothed_view(self):
        mock_investment = MagicMock(spec=QuantumAIInvestment)
        mock_investment.amount = Decimal("1000")
        mock_investment.total_payouts = Decimal("200")
        mock_investment.accrued_profit = Decimal("50")
        mock_investment.fund.name = "Master Fund"
        mock_investment.share_percentage = Decimal("10.0")
        mock_investment.status = "active"

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = [mock_investment]

        with patch(
            "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
        ):
            result = QuantumAIFundService.get_user_dashboard("testuser")

            assert result["total_invested"] == Decimal("1000")
            assert result["total_profit_paid"] == Decimal("200")
            assert result["current_accrued_profit"] == Decimal("50")

    def test_dashboard_no_investments(self):
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = []

        with patch(
            "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
        ):
            result = QuantumAIFundService.get_user_dashboard("testuser")
            assert result["total_invested"] == 0
            assert result["investments"] == []

    def test_dashboard_zero_roi_when_no_investment(self):
        mock_qs = MagicMock()
        mock_qs.select_related.return_value = []

        with patch(
            "services.quantum_ai_fund.QuantumAIInvestment.objects.filter", return_value=mock_qs
        ):
            result = QuantumAIFundService.get_user_dashboard("testuser")
            assert result["roi_percentage"] == Decimal("0")
