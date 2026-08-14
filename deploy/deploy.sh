#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Torgovo Zero-Downtime Deploy
# =============================================================================
# Uses Docker blue-green pattern: spin up new containers alongside old,
# run health checks, then swap traffic and tear down old.
#
# Usage: ./deploy/deploy.sh [--rollback]
# =============================================================================

cd "$(dirname "$0")/.."
PROJECT="torgovo"
COMPOSE_FILE="docker-compose.yml"
GREEN_COMPOSE="docker-compose.green.yml"
HEALTH_CHECK_URL="http://localhost:8000/ht/"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "=== Torgovo Zero-Downtime Deploy ==="

# Step 1: Pull latest images
docker compose -f "${COMPOSE_FILE}" pull

# Step 2: Run migrations (safe to run while old containers serve traffic)
echo "--- Running Migrations ---"
docker compose -f "${COMPOSE_FILE}" run --rm web python manage.py migrate --noinput
docker compose -f "${COMPOSE_FILE}" run --rm web python manage.py collectstatic --noinput --clear

# Step 3: Build green stack
echo "--- Deploying Green Stack ---"
docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" up -d --no-deps --scale web=0 web
docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" up -d --no-deps web-green

# Step 4: Health check green
echo "--- Health Check Green ---"
for i in $(seq 1 ${MAX_RETRIES}); do
    if curl -sf "${HEALTH_CHECK_URL}" > /dev/null 2>&1; then
        echo "   Green healthy after ${i}s"
        break
    fi
    if [ "${i}" -eq "${MAX_RETRIES}" ]; then
        echo "   Health check failed. Rolling back..."
        docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" down web-green
        exit 1
    fi
    sleep "${RETRY_INTERVAL}"
done

# Step 5: Swap traffic (scale blue down, green up)
echo "--- Switching Traffic ---"
docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" up -d --no-deps --scale web=0 web-green
docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" up -d --no-deps web=1
docker compose -f "${COMPOSE_FILE}" -f "${GREEN_COMPOSE}" rm -f web-green

# Step 6: Restart celery (graceful)
echo "--- Restarting Celery ---"
docker compose -f "${COMPOSE_FILE}" exec celery-worker celery -A config.celery control shutdown 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" up -d --no-deps celery-worker celery-beat

echo "=== Deploy Complete ==="
