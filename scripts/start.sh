#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

VENV="$PROJECT_DIR/venv"
ACTIVATE="$VENV/bin/activate"

# --- 1. Validate / generate FERNET_KEY ---
CURRENT_KEY="${FERNET_KEY:-$(grep '^FERNET_KEY=' .env 2>/dev/null | cut -d= -f2-)}"
python3 -c "
import re, sys
from cryptography.fernet import Fernet
key = '$CURRENT_KEY'
if re.match(r'^[A-Za-z0-9+/=]{44}$', key):
    try:
        Fernet(key)
        sys.exit(0)
    except Exception:
        pass
print(Fernet.generate_key().decode())
" 2>/dev/null || python3 -c "
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
" > /tmp/_new_fernet_key.tmp

NEW_KEY=$(cat /tmp/_new_fernet_key.tmp 2>/dev/null)
rm -f /tmp/_new_fernet_key.tmp

if [ -n "$NEW_KEY" ]; then
    if [ -f .env ] && grep -q '^FERNET_KEY=' .env; then
        sed -i "s|^FERNET_KEY=.*|FERNET_KEY=$NEW_KEY|" .env
    else
        echo "FERNET_KEY=$NEW_KEY" >> .env
    fi
    echo "Generated valid FERNET_KEY"
else
    echo "FERNET_KEY is valid"
fi

# --- 2. Source .env and activate venv ---
export $(grep -v '^\s*#' .env | grep -v '^\s*$' | xargs)
source "$ACTIVATE"

# --- 3. Start Postgres ---
start_postgres_docker() {
    echo "Trying Docker Postgres..."
    docker compose up -d db
    for i in $(seq 1 30); do
        if docker compose ps db 2>/dev/null | grep -q "healthy"; then
            echo "Postgres is healthy (Docker)"
            return 0
        fi
        sleep 2
    done
    return 1
}

start_postgres_local() {
    echo "Trying local Postgres..."
    PG_CLUSTER=$(pg_lsclusters -h 2>/dev/null | head -1)
    if [ -n "$PG_CLUSTER" ]; then
        VERSION=$(echo "$PG_CLUSTER" | awk '{print $1}')
        NAME=$(echo "$PG_CLUSTER" | awk '{print $2}')
        sudo pg_ctlcluster "$VERSION" "$NAME" start 2>/dev/null || true
    elif command -v pg_ctl &>/dev/null; then
        # torgovo2's dedicated user-space cluster (port pinned in postgresql.conf)
        PGDATA="${PGDATA:-/home/arcore/pgdata}"
        if [ -f "$PGDATA/PG_VERSION" ]; then
            pg_ctl start -D "$PGDATA" -l "$PGDATA/server.log" 2>/dev/null || true
        fi
    fi
    for i in $(seq 1 15); do
        if pg_isready -q -h 127.0.0.1 -p "${DB_PORT:-5444}" 2>/dev/null; then
            echo "Postgres is running (local on ${DB_PORT:-5444})"
            return 0
        fi
        sleep 2
    done
    return 1
}

if pg_isready -q -h 127.0.0.1 -p "${DB_PORT:-5444}" 2>/dev/null; then
    echo "Postgres is already running"
elif command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    start_postgres_docker || start_postgres_local || {
        echo "WARNING: Could not start Postgres. Run it manually then re-run this script."
        exit 1
    }
else
    start_postgres_local || {
        echo "WARNING: Could not start Postgres. Run it manually then re-run this script."
        exit 1
    }
fi

# --- 4. Create database if it doesn't exist ---
echo "Ensuring database exists..."
PG_SOCK="/run/user/$(id -u)"
DB_EXISTS=$(psql -h "$PG_SOCK" -p "${DB_PORT:-5444}" -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME:-torgovo}'" 2>/dev/null || true)
if [ "$DB_EXISTS" != "1" ]; then
    createdb -h "$PG_SOCK" -p "${DB_PORT:-5444}" -U postgres "${DB_NAME:-torgovo}" 2>/dev/null || \
        sudo -u postgres createdb "${DB_NAME:-torgovo}" 2>/dev/null || true
fi

# --- 5. Run migrations ---
echo "Running migrations..."
python manage.py migrate --noinput

# --- 6. Check for plaintext fund keys ---
echo "Checking for plaintext QuantumAIFund keys..."
python manage.py encrypt_quantum_fund_keys --dry-run 2>/dev/null || true

# --- 7. Start dev server ---
# Dedicated torgovo2 backend port (2026-10-18) — must match BACKEND_PORT in .env
BACKEND_PORT="${BACKEND_PORT:-8600}"
echo ""
echo "Starting development server on http://0.0.0.0:${BACKEND_PORT}"
echo ""
python manage.py runserver "0.0.0.0:${BACKEND_PORT}"
