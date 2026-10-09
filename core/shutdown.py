"""
Graceful shutdown handler for Django.

Registers signal handlers for SIGTERM/SIGINT so the process finishes
in-flight requests before exiting. Works with gunicorn, uvicorn, and
standalone Django runserver.
"""

import logging
import signal
import threading

logger = logging.getLogger("apps")

# Flag to tell request-processing loops to stop
_shutdown_event = threading.Event()


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    _shutdown_event.set()


def is_shutting_down() -> bool:
    """Check if a shutdown signal has been received."""
    return _shutdown_event.is_set()


def register_shutdown_handlers():
    """Register SIGTERM/SIGINT handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    logger.info("Graceful shutdown handlers registered")


# Auto-register when module is imported
register_shutdown_handlers()
