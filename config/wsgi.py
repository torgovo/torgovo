"""
WSGI config for Torgovo Crypto Trading Platform
"""

import logging
import os
import signal
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

logger = logging.getLogger("apps")

application = get_wsgi_application()


# Graceful shutdown: let gunicorn finish in-flight requests before exiting.
def _shutdown_handler(signum, frame):
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} in WSGI process (PID {os.getpid()}), shutting down...")
    # Exit with 0 so gunicorn's master process knows to stop respawning
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)
