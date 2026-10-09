"""
Celery tasks for investment fund operations.

Handles payout processing for Quantum AI fund investors.
"""

import logging

from celery import shared_task

logger = logging.getLogger("investments.tasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_fund_payouts(self):
    """
    FIN-1: Process accrued profit payouts for all active Quantum AI funds.

    Moves accrued_profit → total_payouts + credits user balance via
    QuantumAIFundService.process_payouts(). Runs daily at 00:05 UTC
    (after distribute_quantum_ai_profits at 00:00 UTC).

    Returns:
        dict with payout_count and total_paid per fund
    """
    from apps.bots.models import QuantumAIFund
    from services.quantum_ai_fund import QuantumAIFundService

    funds = QuantumAIFund.objects.filter(is_active=True, is_deleted=False)
    results = []

    for fund in funds:
        try:
            result = QuantumAIFundService.process_payouts(str(fund.id))
            results.append({"fund_id": str(fund.id), "fund_name": fund.name, **result})
            logger.info(
                f"Payouts processed for {fund.name}: "
                f"{result['payout_count']} investors, ${result['total_paid']:,.2f}"
            )
        except Exception as e:
            logger.exception(f"Payout processing failed for fund {fund.name}: {e}")
            # Don't raise — continue processing other funds

    total_paid = sum(r.get("total_paid", 0) for r in results)
    total_count = sum(r.get("payout_count", 0) for r in results)
    logger.info(f"All payouts complete: {total_count} investors, ${total_paid:,.2f}")
    return {"funds_processed": len(results), "total_payouts": total_count, "total_paid": total_paid}
