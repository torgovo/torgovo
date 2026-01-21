"""
Celery tasks for trading bots.

These tasks handle asynchronous bot execution.
"""
from celery import shared_task
import logging

logger = logging.getLogger('trading.tasks')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_trading_bot(self, bot_id: str):
    """
    Run a single iteration of a trading bot.

    This task is called periodically by Celery Beat or triggered manually.

    Args:
        bot_id: UUID of the BotConfiguration

    Returns:
        Execution result dict
    """
    from .managers import run_bot

    try:
        result = run_bot(bot_id)

        if not result.get('success') and result.get('error'):
            logger.error(f"Bot {bot_id} execution failed: {result['error']}")
            # Don't retry on non-transient errors
            if 'not found' in result['error'].lower():
                return result
            raise self.retry(exc=Exception(result['error']))

        return result

    except Exception as e:
        logger.error(f"Task error for bot {bot_id}: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task
def start_bot(bot_id: str):
    """
    Start a trading bot.

    Updates the bot status and schedules periodic execution.

    Args:
        bot_id: UUID of the BotConfiguration
    """
    from .models import BotConfiguration

    try:
        bot_config = BotConfiguration.objects.get(id=bot_id)
        bot_config.status = 'active'
        bot_config.save(update_fields=['status'])

        logger.info(f"Bot {bot_id} started")
        return {'success': True, 'status': 'started'}

    except BotConfiguration.DoesNotExist:
        return {'success': False, 'error': f'Bot not found: {bot_id}'}


@shared_task
def stop_bot(bot_id: str):
    """
    Stop a trading bot.

    Updates the bot status to stopped.

    Args:
        bot_id: UUID of the BotConfiguration
    """
    from .models import BotConfiguration

    try:
        bot_config = BotConfiguration.objects.get(id=bot_id)
        bot_config.status = 'stopped'
        bot_config.save(update_fields=['status'])

        logger.info(f"Bot {bot_id} stopped")
        return {'success': True, 'status': 'stopped'}

    except BotConfiguration.DoesNotExist:
        return {'success': False, 'error': f'Bot not found: {bot_id}'}


@shared_task
def check_all_active_bots():
    """
    Check and run all active bots.

    This is typically scheduled to run every minute via Celery Beat.
    """
    from .models import BotConfiguration

    active_bots = BotConfiguration.objects.filter(
        status='active',
        is_active=True
    ).values_list('id', flat=True)

    results = []
    for bot_id in active_bots:
        # Schedule each bot to run
        run_trading_bot.delay(str(bot_id))
        results.append(str(bot_id))

    logger.info(f"Scheduled {len(results)} active bots for execution")
    return {'scheduled_bots': results, 'count': len(results)}
