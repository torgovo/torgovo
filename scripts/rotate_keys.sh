#!/usr/bin/env bash
# rotate_keys.sh — Rotate exchange API keys and Fernet encryption key.
#
# Usage:
#   ./scripts/rotate_keys.sh [--dry-run]
#
# Steps:
#   1. Generate a new FERNET_KEY
#   2. Re-encrypt all stored exchange credentials with the new key
#   3. Print instructions for updating .env with the new key
#
# WARNING: Run this during a maintenance window. The app must be
#          restarted after rotation for the new key to take effect.

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

echo "=== Torgovo2 Key Rotation ==="
echo ""

# 1. Generate new Fernet key
NEW_FERNET=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "New FERNET_KEY: $NEW_FERNET"

if $DRY_RUN; then
    echo ""
    echo "[DRY RUN] Would re-encrypt credentials and update .env"
    echo "  New key: $NEW_FERNET"
    echo "  After updating .env, restart: docker compose restart app"
    exit 0
fi

# 2. Re-encrypt exchange credentials (if manage.py is available)
if [[ -f manage.py ]]; then
    echo ""
    echo "Re-encrypting exchange credentials..."
    OLD_KEY="${FERNET_KEY:-}"
    if [[ -n "$OLD_KEY" ]]; then
        python manage.py reencrypt_credentials --old-key "$OLD_KEY" --new-key "$NEW_FERNET" --dry-run
        echo ""
        read -p "Proceed with re-encryption? [y/N] " confirm
        if [[ "$confirm" == [yY] ]]; then
            python manage.py reencrypt_credentials --old-key "$OLD_KEY" --new-key "$NEW_FERNET"
            echo "Re-encryption complete."
        else
            echo "Aborted."
            exit 1
        fi
    else
        echo "WARNING: FERNET_KEY not set in environment. Skipping re-encryption."
    fi
fi

# 3. Instructions
echo ""
echo "=== Next Steps ==="
echo "1. Update .env:"
echo "   FERNET_KEY=$NEW_FERNET"
echo ""
echo "2. Rotate exchange API keys manually:"
echo "   - Binance: https://www.binance.com/en/my/settings/api-management"
echo "   - Bybit:   https://www.bybit.com/app/user/api-management"
echo "   Update the new keys in .env"
echo ""
echo "3. Restart the application:"
echo "   docker compose down && docker compose up -d"
echo ""
echo "4. Verify:"
echo "   curl http://localhost:8000/health/"
echo ""
echo "Done. OLD KEY: ${OLD_KEY:-<not set>}"
