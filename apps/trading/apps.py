"""App configuration for the trading app.

``ready()`` owns graceful-shutdown wiring (Phase 6b). A Celery worker needs
an *extra* registration pass because the boot order is:

    WorkController.__init__      -> loader.init_worker()
                                 -> import_default_modules()
                                 -> DjangoFixup.validate_models()
                                 -> django.setup()  == TradingConfig.ready()
    Worker.start -> blueprint    -> Worker.on_start()
                                 -> install_platform_tweaks()
                                 -> signal(SIGTERM, celery._handle_request)

i.e. Celery overwrites SIGTERM *after* Django's ``ready()`` has already run.
``worker_ready`` (main process) and ``worker_process_init`` (every pool child)
both fire after that overwrite, so they are the correct re-install points and
let us chain Celery's handler instead of discarding it.
"""

import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger("trading.managers")


def _is_celery_worker(argv=None) -> bool:
    """True when this process was launched as a Celery *worker*.

    Recognises ``celery -A config worker ...`` and ``python -m celery worker
    ...``.  Returns False for ``celery beat`` / ``celery inspect`` / plain
    ``manage.py`` commands / pytest (so tests never touch signal handlers).
    """
    raw = list(sys.argv if argv is None else argv)
    if not raw:
        return False
    args = [str(a).lower() for a in raw]
    if "worker" not in args:
        return False
    # `celery -A config worker ...` (program name is the celery entry point)
    if os.path.basename(args[0]).startswith("celery"):
        return True
    # `python -m celery worker ...`
    try:
        return args[args.index("-m") + 1] == "celery"
    except (ValueError, IndexError):
        return False


def _install_celery_shutdown_hooks() -> None:
    """Re-install our SIGTERM/SIGINT handler after Celery has claimed them.

    Deferred (inside a function) so ``celery`` is only imported in the one
    process that needs it — tests, manage.py and gunicorn never pay for it.
    """
    from celery import signals

    from apps.trading.engines.execution import _install_shutdown_handler

    def _reinstall(**_kwargs):
        # Idempotent: safe if both hooks fire in the same process.
        if not _install_shutdown_handler():
            logger.warning("Could not install shutdown handler (not main thread?)")

    # weak=False: these are plain module-level functions and would otherwise
    # be garbage-collected before the signal ever fires.
    signals.worker_ready.connect(_reinstall, weak=False)
    signals.worker_process_init.connect(_reinstall, weak=False)
    logger.debug("Celery shutdown hooks installed (worker_ready, worker_process_init)")


def _install_celery_recovery_hook() -> None:
    """Dispatch Phase 4 boot recovery once the worker is ready.

    ``worker_ready`` fires exactly once in the main process after the pool
    starts — deliberately NOT ``worker_process_init``, which fires per pool
    child and would re-dispatch every restore (duplicate engines fighting
    over one position). The receiver swallows its own errors so a recovery
    failure can never take the worker down.
    """
    from celery import signals

    def _recover(**_kwargs):
        try:
            from apps.trading.state import recover_running_bots

            summary = recover_running_bots()
            logger.info(
                "Boot recovery: %s recovered, %s skipped, %s errors",
                len(summary.get("recovered", [])),
                len(summary.get("skipped", [])),
                len(summary.get("errors", [])),
            )
        except Exception:
            logger.exception("Boot recovery hook failed (non-fatal)")

    # weak=False: plain module-level closure, would be GC'd otherwise.
    signals.worker_ready.connect(_recover, weak=False)
    logger.debug("Celery boot-recovery hook installed (worker_ready)")


class TradingConfig(AppConfig):
    """Django app configuration for the trading app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.trading"
    verbose_name = "Trading"

    def ready(self):
        """Import signals when app is ready."""
        # Celery path only — the legacy RUN_MAIN / gunicorn gate stays inside
        # execution.py so existing runserver & gunicorn behaviour is unchanged.
        if _is_celery_worker():
            try:
                _install_celery_shutdown_hooks()
            except Exception:  # never take the worker down over signal wiring
                logger.exception("Failed to install Celery shutdown hooks")
            try:
                _install_celery_recovery_hook()
            except Exception:  # never take the worker down over signal wiring
                logger.exception("Failed to install Celery boot-recovery hook")
