"""
Celery tasks for trading bots.

These tasks handle asynchronous bot execution using actual bot models
from apps/bots/ (GridBot, MartingaleBot, SignalBot).
"""
from celery import shared_task
import logging

logger = logging.getLogger('trading.tasks')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_trading_bot(self, bot_id: str, bot_type: str = 'grid'):
    """
    Run a single iteration of a trading bot.

    Args:
        bot_id: UUID of the bot
        bot_type: 'grid', 'martingale', 'signal', or 'quantum_ai'

    Returns:
        Execution result dict
    """
    from .engines.execution import run_bot

    try:
        result = run_bot(bot_id, bot_type=bot_type)

        if not result.get('success') and result.get('error'):
            logger.error(f"Bot {bot_id} execution failed: {result['error']}")
            if 'not found' in result['error'].lower():
                return result
            raise self.retry(exc=Exception(result['error']))

        return result

    except Exception as e:
        logger.error(f"Task error for bot {bot_id}: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task
def start_bot(bot_id: str, bot_type: str = 'grid'):
    """
    Start a trading bot (updates is_running state).

    Args:
        bot_id: UUID of the bot
        bot_type: 'grid' or 'martingale'
    """
    from django.utils import timezone

    try:
        bot = _get_bot_instance(bot_id, bot_type)
        if bot is None:
            return {'success': False, 'error': f'Bot not found: {bot_id}'}

        bot.is_running = True
        bot.started_at = timezone.now()
        bot.save(update_fields=['is_running', 'started_at'])

        logger.info(f"Bot {bot_id} ({bot_type}) started")
        return {'success': True, 'status': 'started'}

    except Exception as e:
        logger.error(f"Error starting bot {bot_id}: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def stop_bot(bot_id: str, bot_type: str = 'grid'):
    """
    Stop a trading bot (updates is_running state).

    Args:
        bot_id: UUID of the bot
        bot_type: 'grid' or 'martingale'
    """
    from django.utils import timezone

    try:
        bot = _get_bot_instance(bot_id, bot_type)
        if bot is None:
            return {'success': False, 'error': f'Bot not found: {bot_id}'}

        bot.is_running = False
        bot.stopped_at = timezone.now()
        bot.save(update_fields=['is_running', 'stopped_at'])

        logger.info(f"Bot {bot_id} ({bot_type}) stopped")
        return {'success': True, 'status': 'stopped'}

    except Exception as e:
        logger.error(f"Error stopping bot {bot_id}: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def check_all_active_bots():
    """
    Check and run all active bots.
    Typically scheduled every minute via Celery Beat.
    """
    from apps.bots.models import GridBot, MartingaleBot

    results = []

    # Schedule running grid bots
    grid_bots = GridBot.objects.filter(
        is_running=True, is_deleted=False
    ).values_list('id', flat=True)
    for bot_id in grid_bots:
        run_trading_bot.delay(str(bot_id), bot_type='grid')
        results.append(str(bot_id))

    # Schedule running martingale bots
    martingale_bots = MartingaleBot.objects.filter(
        is_running=True, is_deleted=False
    ).values_list('id', flat=True)
    for bot_id in martingale_bots:
        run_trading_bot.delay(str(bot_id), bot_type='martingale')
        results.append(str(bot_id))

    logger.info(f"Scheduled {len(results)} active bots for execution")
    return {'scheduled_bots': results, 'count': len(results)}


def _get_bot_instance(bot_id: str, bot_type: str):
    """Helper to get the right bot model instance."""
    try:
        if bot_type == 'grid':
            from apps.bots.models import GridBot
            return GridBot.objects.get(id=bot_id)
        elif bot_type == 'martingale':
            from apps.bots.models import MartingaleBot
            return MartingaleBot.objects.get(id=bot_id)
        elif bot_type == 'signal':
            from apps.bots.models import SignalBot
            return SignalBot.objects.get(id=bot_id)
    except Exception:
        return None


@shared_task
def distribute_quantum_ai_profits():
    """
    Fortnightly task: distribute Quantum AI fund profits proportionally to all
    active investors based on their share_percentage.

    Flow:
    1. For each active QuantumAIFund, calculate distributable profit
       (total_profit * shown_percentage / 100)
    2. For each active QuantumAIInvestment in that fund, credit their share
    3. Record a QuantumWeeklyProfit entry for audit trail
    4. Reset fund.total_profit to 0 after distribution

    Users only see their accrued_profit balance — no trade details exposed.
    """
    from decimal import Decimal
    from django.utils import timezone
    from apps.bots.models import QuantumAIFund, QuantumAIInvestment, QuantumWeeklyProfit

    funds = QuantumAIFund.objects.filter(is_active=True, is_deleted=False)
    total_distributions = 0

    for fund in funds:
        if fund.total_profit <= 0:
            logger.info(f"Fund {fund.name}: no profit to distribute (total_profit={fund.total_profit})")
            continue

        # Amount to show users = total_profit * shown_percentage%
        distributable = fund.total_profit * (fund.shown_percentage / Decimal('100'))
        logger.info(f"Fund {fund.name}: distributing {distributable} USDT to investors")

        active_investments = QuantumAIInvestment.objects.filter(
            fund=fund, status='active', is_deleted=False
        )

        now = timezone.now()
        week_start = now.date()
        week_end = (now + timezone.timedelta(days=14)).date()

        for investment in active_investments:
            # Recalculate share percentage in case fund total changed
            if fund.total_deposits > 0:
                investment.share_percentage = (investment.amount / fund.total_deposits) * 100

            user_profit = (distributable * investment.share_percentage) / Decimal('100')
            investment.accrued_profit += user_profit
            investment.total_payouts += user_profit
            investment.save(update_fields=['share_percentage', 'accrued_profit', 'total_payouts', 'updated_at'])

            # Audit trail
            QuantumWeeklyProfit.objects.update_or_create(
                user=investment.user,
                fund=fund,
                week_start=week_start,
                defaults={
                    'week_end': week_end,
                    'total_deposited': investment.amount,
                    'realized_pnl': user_profit,
                    'user_share_percent': investment.share_percentage,
                    'is_distributed': True,
                    'distributed_at': now,
                }
            )
            total_distributions += 1

        # Reset fund profit after distribution
        fund.total_profit = Decimal('0')
        fund.save(update_fields=['total_profit', 'updated_at'])
        logger.info(f"Fund {fund.name}: distribution complete, profit reset to 0")

    logger.info(f"Quantum AI profit distribution complete: {total_distributions} investors credited")
    return {'distributed_to': total_distributions}
