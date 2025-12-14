"""
Quantum AI fund profit distribution service.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.bots.models import QuantumAIFund, QuantumAIInvestment
from apps.payments.models import PaymentTransaction
from apps.users.models import UserBalance  # Assuming you have this model

logger = logging.getLogger(__name__)


class QuantumAIFundService:
    """
    Service for managing Quantum AI fund and profit distributions.
    """

    @staticmethod
    @transaction.atomic
    def update_fund_performance(fund_id: str, new_total_value: Decimal):
        """
        Update fund performance (called manually by admin or via automation).

        Args:
            fund_id: UUID of QuantumAIFund
            new_total_value: Current total value of fund in USDT
        """
        fund = QuantumAIFund.objects.select_for_update().get(id=fund_id)

        old_total_value = fund.total_fund_value
        fund.total_fund_value = new_total_value

        # Calculate profit since inception
        fund.total_profit = new_total_value - fund.total_deposits

        fund.last_trade_at = timezone.now()
        fund.save()

        logger.info(f"Updated Quantum AI fund: {fund.name} to ${new_total_value:,.2f}")

        # Optionally trigger profit distribution if profit increased
        if fund.total_profit > 0:
            QuantumAIFundService.calculate_profit_distribution(fund_id)

        return fund

    @staticmethod
    def calculate_profit_distribution(fund_id: str):
        """
        Calculate profit share for each investor (does not pay out yet).
        Creates accrual records that admin can later approve for payout.
        """
        fund = QuantumAIFund.objects.get(id=fund_id)

        if fund.total_profit <= 0:
            logger.info("No profit to distribute")
            return

        profit_to_distribute = fund.calculate_profit_to_distribute()

        # Get all active investments
        active_investments = QuantumAIInvestment.objects.filter(
            fund=fund,
            status='active'
        ).select_related('user')

        if not active_investments.exists():
            logger.warning("No active investments found")
            return

        # Calculate each investor's share
        distribution_records = []
        for investment in active_investments:
            user_share = investment.calculate_profit_share()

            if user_share > 0:
                # Update accrued profit (not paid yet)
                investment.accrued_profit += user_share
                investment.save()

                distribution_records.append({
                    'user': investment.user.email,
                    'amount': user_share,
                    'investment': investment.amount,
                    'share_percentage': investment.share_percentage,
                })

        logger.info(f"Calculated profit distribution: ${profit_to_distribute:,.2f}")
        logger.info(f"Distribution records: {distribution_records}")

        return distribution_records

    @staticmethod
    @transaction.atomic
    def process_payouts(fund_id: str, payout_date=None):
        """
        Process actual payouts to users (admin-triggered).
        Moves accrued_profit to total_payouts and credits user balance.
        """
        if payout_date is None:
            payout_date = timezone.now()

        fund = QuantumAIFund.objects.select_for_update().get(id=fund_id)

        # Get all investments with accrued profit
        investments = QuantumAIInvestment.objects.filter(
            fund=fund,
            accrued_profit__gt=0
        ).select_for_update()

        total_paid = Decimal('0')
        payout_count = 0

        for investment in investments:
            payout_amount = investment.accrued_profit

            # Update investment
            investment.total_payouts += payout_amount
            investment.accrued_profit = Decimal('0')
            investment.save()

            # Credit user balance
            try:
                balance, created = UserBalance.objects.get_or_create(
                    user=investment.user,
                    currency='USDT',
                    defaults={'available': Decimal('0'), 'hold': Decimal('0')}
                )
                balance.available += payout_amount
                balance.save()

                # Log the transaction
                PaymentTransaction.objects.create(
                    user=investment.user,
                    transaction_type='quantum_ai_payout',
                    amount=payout_amount,
                    currency='USDT',
                    description=f"Quantum AI profit distribution for {payout_date.date()}",
                    status='completed'
                )

                total_paid += payout_amount
                payout_count += 1

            except Exception as e:
                logger.error(f"Error processing payout for {investment.user.email}: {e}")
                # Rollback this investment but continue others
                investment.total_payouts -= payout_amount
                investment.accrued_profit = payout_amount
                investment.save()

        logger.info(f"Processed {payout_count} payouts totaling ${total_paid:,.2f}")
        return {
            'payout_count': payout_count,
            'total_paid': total_paid,
        }

    @staticmethod
    def get_user_dashboard(user):
        """
        Get user's Quantum AI investment dashboard.
        """
        from django.db.models import Sum

        investments = QuantumAIInvestment.objects.filter(
            user=user
        ).select_related('fund')

        total_invested = sum(i.amount for i in investments)
        total_profit_paid = sum(i.total_payouts for i in investments)
        current_accrued = sum(i.accrued_profit for i in investments)

        return {
            'total_invested': total_invested,
            'total_profit_paid': total_profit_paid,
            'current_accrued_profit': current_accrued,
            'total_value': total_invested + total_profit_paid + current_accrued,
            'roi_percentage': (total_profit_paid / total_invested * 100) if total_invested > 0 else 0,
            'investments': [
                {
                    'fund_name': i.fund.name,
                    'amount': i.amount,
                    'share': f"{i.share_percentage:.2f}%",
                    'status': i.status,
                    'deposited_at': i.deposited_at,
                    'total_payouts': i.total_payouts,
                    'accrued_profit': i.accrued_profit,
                }
                for i in investments
            ]
        }