"""
Celery tasks for trading bots.

These tasks handle asynchronous bot execution using actual bot models
from apps/bots/ (GridBot, MartingaleBot, SignalBot).
"""
from celery import shared_task
import logging

logger = logging.getLogger('trading.tasks')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_trading_bot(self, bot_id: str, bot_type: str = 'grid', restore_mode: bool = False):
    """
    Run a single iteration of a trading bot.

    Args:
        bot_id: UUID of the bot
        bot_type: 'grid', 'martingale', 'signal', or 'quantum_ai'
        restore_mode: If True, attach to existing position instead of entry eval

    Returns:
        Execution result dict
    """
    from .engines.execution import run_bot

    try:
        result = run_bot(bot_id, bot_type=bot_type, restore_mode=restore_mode)

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

    # Schedule running quantum AI bots
    from apps.bots.models import QuantumAIBot
    quantum_bots = QuantumAIBot.objects.filter(
        is_running=True, is_deleted=False
    ).values_list('id', flat=True)
    for bot_id in quantum_bots:
        run_trading_bot.delay(str(bot_id), bot_type='quantum_ai')
        results.append(str(bot_id))

    logger.info(f"Scheduled {len(results)} active bots for execution")
    return {'scheduled_bots': results, 'count': len(results)}


@shared_task
def check_stale_bots():
    """
    Find bots that are marked running but haven't sent a heartbeat in > 5 minutes.
    
    - If an open position exists on the exchange → restart in restore_mode
      (attaches monitoring threads without placing new entry orders)
    - If no open position → mark is_running=False so normal restart works next time
    
    Runs every 2 minutes via Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=5)
    models_to_check = [
        ('grid', 'GridBot'),
        ('martingale', 'MartingaleBot'),
        ('quantum_ai', 'QuantumAIBot'),
    ]
    restored = 0
    stopped = 0
    errors = 0

    for bot_type, model_name in models_to_check:
        try:
            from apps.bots.models import GridBot, MartingaleBot, QuantumAIBot
            model_map = {
                'GridBot': GridBot,
                'MartingaleBot': MartingaleBot,
                'QuantumAIBot': QuantumAIBot,
            }
            model = model_map[model_name]

            # Bots with stale heartbeat
            stale_bots = model.objects.filter(
                is_running=True, is_deleted=False,
                last_heartbeat__lt=cutoff
            )

            # Bots that have never sent a heartbeat but started > 5 min ago
            never_heartbeat = model.objects.filter(
                is_running=True, is_deleted=False,
                last_heartbeat__isnull=True,
                started_at__lt=cutoff
            )

            for bot in list(stale_bots) + list(never_heartbeat):
                try:
                    _handle_stale_bot(bot, bot_type)
                    restored += 1
                except Exception as e:
                    logger.error(f"Failed to recover stale bot {bot.id}: {e}")
                    errors += 1
        except Exception as e:
            logger.error(f"Error checking {model_name} stale bots: {e}")
            errors += 1

    logger.info(f"Stale bot check complete: {restored} restored, {stopped} stopped, {errors} errors")
    return {'restored': restored, 'stopped': stopped, 'errors': errors}


def _handle_stale_bot(bot, bot_type):
    """
    Handle a stale bot: check for open position and recover or stop.
    """
    from django.utils import timezone
    from decimal import Decimal
    has_position = False
    exchange_name = bot.exchange_name
    trading_pair = bot.trading_pair
    bot_id = str(bot.id)

    # Try to check for open position on exchange
    try:
        if bot_type == 'quantum_ai':
            from apps.bots.models import QuantumAIBot, QuantumAIFund
            from core.utils import decrypt_api_key
            fund = QuantumAIFund.objects.get(id=bot.fund_id)
            api_key = decrypt_api_key(fund.master_api_key)
            secret_key = decrypt_api_key(fund.master_secret_key)
            passphrase = decrypt_api_key(fund.master_passphrase) if fund.master_passphrase else ''
            from ..trading.exchanges import get_adapter
            adapter = get_adapter(
                exchange_name=exchange_name,
                credentials={
                    'api_key': api_key,
                    'secret_key': secret_key,
                    'passphrase': passphrase,
                },
                demo_mode=False,
            )
            position = adapter.fetch_position(trading_pair)
            has_position = position and float(position.get('contracts', 0)) > 0
        else:
            # User bots: need user credentials
            from apps.exchanges.models import ExchangeCredentials
            credentials = ExchangeCredentials.objects.get(
                user=bot.user,
                exchange_name=exchange_name,
                is_active=True
            )
            creds = credentials.get_decrypted_credentials()
            from ..trading.exchanges import get_adapter
            adapter = get_adapter(
                exchange_name=exchange_name,
                credentials=creds,
                demo_mode=credentials.is_testnet,
            )
            position = adapter.fetch_position(trading_pair)
            has_position = position and float(position.get('contracts', 0)) > 0
    except Exception as e:
        logger.warning(f"Could not check position for stale bot {bot_id}: {e}")
        # If we can't check the exchange, safest to just mark stopped
        # so next user action starts fresh
        has_position = False

    if has_position:
        logger.warning(f"Stale bot {bot_id} has open position — restarting in restore_mode")
        bot.is_running = False
        bot.last_heartbeat = timezone.now()
        bot.save(update_fields=['is_running', 'last_heartbeat', 'updated_at'])
        run_trading_bot.delay(bot_id, bot_type, restore_mode=True)
        try:
            from core.telegram_service import TelegramService
            TelegramService.send_admin_alert(
                f"🚨 Bot Restored\n\n"
                f"Bot {bot.bot_name} ({bot_id}) was restored after worker crash.\n"
                f"Type: {bot_type}\n"
                f"Pair: {bot.trading_pair}\n"
                f"Exchange: {bot.exchange_name}\n"
                f"Mode: restore (attached to existing position)\n"
                f"Action: Monitoring threads re-started, no new entry orders."
            )
        except Exception as e:
            logger.warning(f"Failed to send admin alert for bot restore: {e}")
    else:
        logger.info(f"Stale bot {bot_id} has no open position — marking stopped")
        bot.is_running = False
        bot.last_heartbeat = timezone.now()
        bot.save(update_fields=['is_running', 'last_heartbeat', 'updated_at'])


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
        elif bot_type == 'quantum_ai':
            from apps.bots.models import QuantumAIBot
            return QuantumAIBot.objects.get(id=bot_id)
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
