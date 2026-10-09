"""
Production health check endpoint.

Returns 200 only when ALL critical subsystems are reachable.
Used by Docker HEALTHCHECK, Kubernetes probes, and load balancers.
"""

import time

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


def _check_db():
    """Verify database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, None
    except Exception as e:
        return False, str(e)


def _check_redis():
    """Verify Redis cache is reachable."""
    try:
        cache.set("healthcheck", "ok", 10)
        val = cache.get("healthcheck")
        return val == "ok", None
    except Exception as e:
        return False, str(e)


def _check_disk(min_free_mb=100):
    """Verify minimum free disk space."""
    import shutil

    try:
        usage = shutil.disk_usage("/")
        free_mb = usage.free / (1024 * 1024)
        if free_mb < min_free_mb:
            return False, f"Only {free_mb:.0f}MB free (min: {min_free_mb}MB)"
        return True, None
    except Exception as e:
        return False, str(e)


@csrf_exempt
@require_GET
def health_check(request):
    """
    Comprehensive health check.

    Returns 200 when all checks pass, 503 when any fails.
    Response always includes individual check results.

    GET /health/
    """
    checks = {}
    all_healthy = True

    # Database
    ok, err = _check_db()
    checks["database"] = {"status": "ok" if ok else "error", "error": err}
    if not ok:
        all_healthy = False

    # Redis
    ok, err = _check_redis()
    checks["redis"] = {"status": "ok" if ok else "error", "error": err}
    if not ok:
        all_healthy = False

    # Disk space
    ok, err = _check_disk()
    checks["disk"] = {"status": "ok" if ok else "error", "error": err}
    if not ok:
        all_healthy = False

    # Uptime
    checks["uptime"] = time.time()

    status_code = 200 if all_healthy else 503
    return JsonResponse(
        {"status": "healthy" if all_healthy else "unhealthy", "checks": checks},
        status=status_code,
    )
