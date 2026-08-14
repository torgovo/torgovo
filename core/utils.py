"""
Utility functions for Torgovo Crypto Trading Platform
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger("apps")


def generate_uuid():
    """Generate a UUID string."""
    return str(uuid.uuid4())


def generate_secret_key(length=32):
    """Generate a random secret key."""
    import secrets

    return secrets.token_urlsafe(length)


def encrypt_api_key(api_key):
    """
    Encrypt API key using Fernet encryption.
    """
    try:
        fernet = Fernet(settings.FERNET_KEY.encode())
        encrypted_key = fernet.encrypt(api_key.encode())
        return encrypted_key.decode()
    except Exception as e:
        logger.error(f"Error encrypting API key: {e}")
        raise


def decrypt_api_key(encrypted_key):
    """
    Decrypt API key using Fernet encryption.
    """
    try:
        fernet = Fernet(settings.FERNET_KEY.encode())
        decrypted_key = fernet.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    except Exception as e:
        logger.error(f"Error decrypting API key: {e}")
        raise


def looks_encrypted(value):
    """
    Check if a value is already Fernet-encrypted.

    Returns True if the value is empty/None (skip), or if it decrypts
    successfully under the current FERNET_KEY. Returns False for values
    that appear to be plaintext and need encryption.

    Safeguard: Fernet tokens always start with ``gAAAAA`` (version + timestamp).
    We check the structure first — if it doesn't look like a Fernet token,
    it's definitely plaintext.  This prevents double-encryption on key
    rotation: old ciphertext still has valid Fernet structure even if the
    key has changed.

    WARNING — key rotation hazard: If the key is rotated, values encrypted
    under the old key will fail decryption here, and looks_encrypted()
    will return False. The caller will then double-encrypt the old ciphertext
    under the new key, producing garbage on the next read.
    Never rotate FERNET_KEY without writing a dedicated re-encryption migration.
    """
    if not value:
        return True
    # Fernet tokens are base64-encoded with a fixed prefix
    if not value.startswith("gAAAAA"):
        return False
    try:
        Fernet(settings.FERNET_KEY.encode()).decrypt(value.encode())
        return True
    except Exception:
        return False


def validate_webhook_signature(payload, signature, secret):
    """
    Validate webhook signature for security.
    """
    try:
        expected_signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Error validating webhook signature: {e}")
        return False


def format_decimal(value, decimal_places=8):
    """
    Format decimal value with specified precision.
    """
    try:
        if isinstance(value, str):
            value = Decimal(value)
        elif not isinstance(value, Decimal):
            value = Decimal(str(value))

        quantize_str = "1." + "0" * decimal_places
        return value.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0")


def calculate_percentage_change(old_value, new_value):
    """
    Calculate percentage change between two values.
    """
    try:
        old_value = Decimal(str(old_value))
        new_value = Decimal(str(new_value))

        if old_value == 0:
            return Decimal("0")

        change = ((new_value - old_value) / old_value) * 100
        return change.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    except (ValueError, TypeError, InvalidOperation, ZeroDivisionError):
        return Decimal("0")


def validate_trading_pair(pair):
    """
    Validate trading pair format (e.g., BTC/USDT).
    """
    if not pair or not isinstance(pair, str):
        return False

    parts = pair.split("/")
    if len(parts) != 2:
        return False

    base, quote = parts
    return base.isalpha() and base.isupper() and quote.isalpha() and quote.isupper()


def parse_float(value, default=0.0):
    """
    Safely parse value to float with default fallback.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return float(default)


def parse_decimal(value, default="0"):
    """
    Safely parse value to Decimal with default fallback.
    """
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal(str(default))


def get_timeframe_minutes(timeframe):
    """
    Convert timeframe string to minutes.
    """
    timeframe_map = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
        "1w": 10080,
    }

    return timeframe_map.get(timeframe.lower(), 1)


def round_to_nearest(value, nearest=0.01):
    """
    Round value to nearest specified amount.
    """
    try:
        value = float(value)
        return round(value / nearest) * nearest
    except (ValueError, TypeError):
        return 0.0


def calculate_grid_levels(price, levels, spacing_percent):
    """
    Calculate grid levels for grid trading.
    """
    try:
        price = float(price)
        spacing = price * (spacing_percent / 100)
        levels = int(levels)

        grid_levels = []
        for i in range(-levels, levels + 1):
            level_price = price + (i * spacing)
            grid_levels.append(level_price)

        return sorted(grid_levels)
    except (ValueError, TypeError):
        return []


def calculate_martingale_levels(base_amount, levels, multiplier=2.0):
    """
    Calculate martingale position sizes.
    """
    try:
        base_amount = float(base_amount)
        levels = int(levels)
        multiplier = float(multiplier)

        position_sizes = []
        for i in range(levels + 1):
            amount = base_amount * (multiplier**i)
            position_sizes.append(amount)

        return position_sizes
    except (ValueError, TypeError):
        return []


def validate_deposit_amount(amount, min_amount=None, max_amount=None):
    """
    Validate deposit amount against limits.
    """
    try:
        amount = Decimal(str(amount))

        if min_amount is not None:
            min_amount = Decimal(str(min_amount))
            if amount < min_amount:
                return False, f"Minimum deposit amount is {min_amount}"

        if max_amount is not None:
            max_amount = Decimal(str(max_amount))
            if amount > max_amount:
                return False, f"Maximum deposit amount is {max_amount}"

        return True, "Valid amount"
    except (ValueError, TypeError, InvalidOperation):
        return False, "Invalid amount format"


def format_currency(amount, currency="USDT", decimal_places=2):
    """
    Format amount as currency string.
    """
    try:
        amount = Decimal(str(amount))

        if currency in ["BTC", "ETH"]:
            decimal_places = 8

        formatted_amount = format_decimal(amount, decimal_places)
        return f"{formatted_amount} {currency}"
    except (ValueError, TypeError, InvalidOperation):
        return f"0.00 {currency}"


def validate_exchange_credentials(exchange_name, api_key, secret_key, passphrase=None):
    """
    Basic validation of exchange credentials format.
    """
    if not exchange_name or not api_key or not secret_key:
        return False, "Missing required credentials"

    # Basic format validation
    if len(api_key) < 10 or len(secret_key) < 10:
        return False, "Invalid credential format"

    # Exchange-specific validation
    if exchange_name.lower() in ["coinbase", "kraken"] and not passphrase:
        return False, "Passphrase required for this exchange"

    return True, "Credentials format valid"


def save_uploaded_file(file, subfolder="uploads"):
    """
    Save uploaded file and return the path.
    """
    try:
        # Generate unique filename
        filename = f"{uuid.uuid4()}_{file.name}"
        filepath = f"{subfolder}/{timezone.now().strftime('%Y/%m/%d')}/{filename}"

        # Save file
        saved_path = default_storage.save(filepath, file)

        return saved_path
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise


def delete_file(file_path):
    """
    Delete file from storage.
    """
    try:
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def calculate_risk_metrics(trades):
    """
    Calculate risk metrics from trade history.
    """
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_profit_loss": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

    total_trades = len(trades)
    winning_trades = 0
    losing_trades = 0
    total_pnl = 0.0
    profits = []
    losses = []

    for trade in trades:
        pnl = float(trade.get("profit_loss", 0))
        total_pnl += pnl

        if pnl > 0:
            winning_trades += 1
            profits.append(pnl)
        elif pnl < 0:
            losing_trades += 1
            losses.append(abs(pnl))

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # Calculate max drawdown (simplified)
    max_drawdown = 0.0
    if len(trades) > 1:
        peak = 0.0
        running_total = 0.0
        for trade in trades:
            pnl = float(trade.get("profit_loss", 0))
            running_total += pnl
            if running_total > peak:
                peak = running_total
            drawdown = peak - running_total
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    # Calculate Sharpe ratio (simplified)
    sharpe_ratio = 0.0
    if profits:
        avg_profit = sum(profits) / len(profits)
        if losses:
            avg_loss = sum(losses) / len(losses)
            if avg_loss > 0:
                sharpe_ratio = avg_profit / avg_loss

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 2),
        "total_profit_loss": round(total_pnl, 2),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
    }


def get_utc_timestamp():
    """
    Get current UTC timestamp.
    """
    return int(timezone.now().timestamp())


def timestamp_to_datetime(timestamp):
    """
    Convert timestamp to datetime.
    """
    try:
        return datetime.fromtimestamp(float(timestamp), tz=dt_timezone.utc)
    except (ValueError, TypeError):
        return timezone.now()


def jsonify_decimal(obj):
    """
    Convert Decimal objects to strings for JSON serialization.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: jsonify_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [jsonify_decimal(item) for item in obj]
    return obj


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
