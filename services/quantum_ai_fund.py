"""
Quantum AI fund — smoothed returns + reserve-backed profit distribution.

Smoothing model:
  If actual return < min  → show min  (reserve covers the gap)
  If min ≤ actual ≤ max  → show actual
  If actual > max         → show max  (excess goes to reserve)

Users ALWAYS see non-negative returns. Admin absorbs all loss.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.bots.models import InvestorPortfolio, QuantumAIFund, ReserveFund
from apps.payments.models import PaymentTransaction
from apps.users.models import UserBalance

logger = logging.getLogger(__name__)


class QuantumAIFundService:

    @staticmethod
    def update_fund_performance(fund_id: str, new_total_value: Decimal):
        """
        Update fund with new total value, then apply smoothing + reserve.

        Args:
            fund_id: UUID of QuantumAIFund
            new_total_value: Current total value in USDT
        """
        with transaction.atomic():
            fund = QuantumAIFund.objects.select_for_update().get(id=fund_id)
            old_total_value = fund.total_fund_value
            fund.total_fund_value = new_total_value
            fund.total_profit = new_total_value - fund.total_deposits
            fund.last_trade_at = timezone.now()
            fund.save()

            logger.info(f"Updated {fund.name}: ${old_total_value:,.2f} → ${new_total_value:,.2f}")

            # Calculate real return since last update
            if old_total_value > 0:
                actual_return_pct = (
                    (new_total_value - old_total_value) / old_total_value
                ) * Decimal("100")
                shown_pct = fund.calculate_smoothed_return(actual_return_pct)
                excess_pct = fund.calculate_excess_return(actual_return_pct)

                logger.info(
                    f"Actual: {actual_return_pct:.2f}% → "
                    f"Shown: {shown_pct:.2f}% | "
                    f"Excess to reserve: {excess_pct:.2f}%"
                )

                # Hit reserve if we showed more than actual (i.e. actual < min)
                if excess_pct < 0:
                    reserve_cover = abs(excess_pct / Decimal("100")) * old_total_value
                    QuantumAIFundService._apply_reserve_cover(fund_id, reserve_cover)

                # Deposit excess into reserve if actual > max
                if excess_pct > 0:
                    reserve_excess = (excess_pct / Decimal("100")) * old_total_value
                    QuantumAIFundService._deposit_excess_to_reserve(fund_id, reserve_excess)

                # Accrue smoothed profit to each investor
                QuantumAIFundService._accrue_smoothed_profit(fund_id, shown_pct)

        return fund

    @staticmethod
    @transaction.atomic
    def _accrue_smoothed_profit(fund_id: str, shown_pct: Decimal):
        """Accrue smoothed profit to each active investor (locked)."""
        fund = QuantumAIFund.objects.select_for_update().get(id=fund_id)
        investments = (
            InvestorPortfolio.objects.filter(fund=fund, status="active")
            .select_for_update()
            .select_related("user")
        )

        if not investments.exists():
            return

        total_shown_value = fund.total_deposits * (shown_pct / Decimal("100"))

        if fund.total_deposits == 0:
            return

        for investment in investments:
            user_share = (investment.amount / fund.total_deposits) * total_shown_value
            investment.accrued_profit += user_share
            investment.save()

        logger.info(
            f"Accrued ${total_shown_value:,.2f} (shown {shown_pct:.2f}%) "
            f"across {investments.count()} investors"
        )

    @staticmethod
    def _apply_reserve_cover(fund_id: str, amount: Decimal):
        """Withdraw from reserve to cover the smoothed floor."""
        try:
            reserve = ReserveFund.objects.select_for_update().get(fund_id=fund_id)
            balance_before = reserve.balance
            if reserve.can_cover(amount):
                reserve.balance -= amount
                reserve.last_withdrawal = timezone.now()
                reserve.save()
                reserve.record_transaction(
                    balance_before,
                    -amount,
                    "shortfall_cover",
                    f"Covered ${amount:,.2f} shortfall (floor smoothing)",
                )
                logger.info(f"Reserve covered ${amount:,.2f} — balance: ${reserve.balance:,.2f}")
            else:
                actual_shortfall = reserve.balance
                reserve.balance = Decimal("0")
                reserve.low_balance_alert_sent = True
                reserve.last_withdrawal = timezone.now()
                reserve.save()
                reserve.record_transaction(
                    balance_before,
                    -actual_shortfall,
                    "shortfall_cover",
                    f"Partial cover — only ${actual_shortfall:,.2f} available "
                    f"of ${amount:,.2f} needed. RESERVE DEPLETED.",
                )
                logger.warning(
                    f"Reserve INSUFFICIENT! Need ${amount:,.2f} "
                    f"but only ${balance_before:,.2f} available. "
                    f"Admin must top up reserve for {fund_id}"
                )
        except ReserveFund.DoesNotExist:
            logger.error(f"No reserve fund found for {fund_id}! Cannot smooth returns.")

    @staticmethod
    def _deposit_excess_to_reserve(fund_id: str, amount: Decimal):
        """Deposit excess profit into reserve."""
        reserve, created = ReserveFund.objects.select_for_update().get_or_create(
            fund_id=fund_id, defaults={"balance": Decimal("0")}
        )
        balance_before = reserve.balance
        reserve.balance += amount
        reserve.last_top_up = timezone.now()
        reserve.low_balance_alert_sent = False
        reserve.save()
        reserve.record_transaction(
            balance_before, amount, "excess_deposit", f"Excess return deposit: ${amount:,.2f}"
        )
        logger.info(f"Reserve received ${amount:,.2f} excess — balance: ${reserve.balance:,.2f}")

    @staticmethod
    @transaction.atomic
    def process_payouts(fund_id: str, payout_date=None):
        """
        Process actual payouts to users.
        Moves accrued_profit → total_payouts + credits user balance.
        """
        if payout_date is None:
            payout_date = timezone.now()

        fund = QuantumAIFund.objects.select_for_update().get(id=fund_id)
        investments = InvestorPortfolio.objects.filter(
            fund=fund, accrued_profit__gt=0
        ).select_for_update()

        total_paid = Decimal("0")
        payout_count = 0

        for investment in investments:
            sid = transaction.savepoint()
            try:
                payout_amount = investment.accrued_profit
                investment.total_payouts += payout_amount
                investment.accrued_profit = Decimal("0")
                investment.save()

                balance, _ = UserBalance.objects.get_or_create(
                    user=investment.user,
                    currency="USDT",
                    defaults={"available": Decimal("0"), "hold": Decimal("0")},
                )
                balance.available += payout_amount
                balance.save()

                PaymentTransaction.objects.create(
                    user=investment.user,
                    transaction_type="quantum_ai_payout",
                    amount=payout_amount,
                    currency="USDT",
                    description=f"Quantum AI distribution — {payout_date.date()}",
                    status="completed",
                )

                total_paid += payout_amount
                payout_count += 1
                transaction.savepoint_commit(sid)

            except Exception as e:
                transaction.savepoint_rollback(sid)
                logger.error(f"Payout failed for {investment.user.email}: {e}")

        logger.info(f"Paid {payout_count} investors ${total_paid:,.2f}")
        return {"payout_count": payout_count, "total_paid": total_paid}

    @staticmethod
    def get_user_dashboard(user):
        """Get user's Quantum AI investment dashboard (smoothed view)."""
        investments = InvestorPortfolio.objects.filter(user=user).select_related("fund")

        total_invested = sum(i.amount for i in investments)
        total_profit_paid = sum(i.total_payouts for i in investments)
        current_accrued = sum(i.accrued_profit for i in investments)

        return {
            "total_invested": total_invested,
            "total_profit_paid": total_profit_paid,
            "current_accrued_profit": current_accrued,
            "total_value": total_invested + total_profit_paid + current_accrued,
            "roi_percentage": (
                (total_profit_paid / total_invested * Decimal("100"))
                if total_invested > 0
                else Decimal("0")
            ),
            "investments": [
                {
                    "fund_name": i.fund.name,
                    "amount": i.amount,
                    "share": f"{i.share_percentage:.2f}%",
                    "status": i.status,
                    "deposited_at": i.deposited_at,
                    "total_payouts": i.total_payouts,
                    "accrued_profit": i.accrued_profit,
                }
                for i in investments
            ],
        }
