import hashlib
import hmac
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from core.utils import (
    calculate_grid_levels,
    calculate_martingale_levels,
    calculate_percentage_change,
    calculate_risk_metrics,
    decrypt_api_key,
    delete_file,
    encrypt_api_key,
    format_currency,
    format_decimal,
    generate_secret_key,
    generate_uuid,
    get_client_ip,
    get_timeframe_minutes,
    get_utc_timestamp,
    jsonify_decimal,
    parse_decimal,
    parse_float,
    round_to_nearest,
    save_uploaded_file,
    timestamp_to_datetime,
    validate_deposit_amount,
    validate_exchange_credentials,
    validate_trading_pair,
    validate_webhook_signature,
)

FERNET_KEY = "K_suZkl9BIXa2xQQlFOj0mTuRVi2Z_bnC0bWmBZysdE="


class TestGenerateUUID:
    def test_returns_string(self):
        result = generate_uuid()
        assert isinstance(result, str)

    def test_valid_uuid_format(self):
        result = generate_uuid()
        uuid.UUID(result)

    def test_unique_values(self):
        results = {generate_uuid() for _ in range(100)}
        assert len(results) == 100


class TestGenerateSecretKey:
    def test_default_length(self):
        key = generate_secret_key()
        assert len(key) == 43

    def test_custom_length(self):
        key = generate_secret_key(64)
        assert len(key) == 86

    def test_urlsafe_characters(self):
        key = generate_secret_key()
        assert all(c.isalnum() or c in {"-", "_"} for c in key)


class TestEncryptDecryptApiKey:
    def _setup_fernet_settings(self, settings):
        settings.FERNET_KEY = FERNET_KEY

    def test_encrypt_returns_string(self, settings):
        self._setup_fernet_settings(settings)
        encrypted = encrypt_api_key("test-api-key-12345")
        assert isinstance(encrypted, str)
        assert encrypted != "test-api-key-12345"

    def test_decrypt_returns_original(self, settings):
        self._setup_fernet_settings(settings)
        original = "my-secret-api-key"
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_round_trip_empty_string(self, settings):
        self._setup_fernet_settings(settings)
        encrypted = encrypt_api_key("")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""

    def test_decrypt_invalid_data(self, settings):
        self._setup_fernet_settings(settings)
        with pytest.raises(Exception):
            decrypt_api_key("not-valid-encrypted-data")

    def test_multiple_keys_different(self, settings):
        self._setup_fernet_settings(settings)
        k1 = encrypt_api_key("key-1")
        k2 = encrypt_api_key("key-2")
        assert k1 != k2

    def test_same_input_produces_different_ciphertext(self, settings):
        self._setup_fernet_settings(settings)
        k1 = encrypt_api_key("same-key")
        k2 = encrypt_api_key("same-key")
        assert k1 != k2


class TestValidateWebhookSignature:
    def test_valid_signature(self):
        payload = '{"event": "test"}'
        secret = "my-webhook-secret"
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        assert validate_webhook_signature(payload, signature, secret) is True

    def test_invalid_signature(self):
        payload = '{"event": "test"}'
        secret = "my-webhook-secret"
        wrong_signature = "abcdef1234567890"
        assert validate_webhook_signature(payload, wrong_signature, secret) is False

    def test_wrong_secret(self):
        payload = '{"event": "test"}'
        signature = hmac.new(b"correct-secret", payload.encode(), hashlib.sha256).hexdigest()
        assert validate_webhook_signature(payload, signature, "wrong-secret") is False

    def test_empty_payload(self):
        signature = hmac.new(b"secret", b"", hashlib.sha256).hexdigest()
        assert validate_webhook_signature("", signature, "secret") is True

    def test_handles_exception_gracefully(self):
        assert validate_webhook_signature(None, "sig", "secret") is False


class TestFormatDecimal:
    @pytest.mark.parametrize(
        "value,places,expected",
        [
            (123.456789, 2, Decimal("123.45")),
            (123.456789, 4, Decimal("123.4567")),
            ("99.9999", 3, Decimal("99.999")),
            (Decimal("10.12345678"), 8, Decimal("10.12345678")),
            (0, 2, Decimal("0.00")),
            (5, 0, Decimal("5")),
        ],
    )
    def test_format_decimal(self, value, places, expected):
        assert format_decimal(value, places) == expected

    def test_negative_value(self):
        assert format_decimal("-50.1234", 2) == Decimal("-50.12")

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("not-a-number", Decimal("0")),
            (None, Decimal("0")),
            ([], Decimal("0")),
        ],
    )
    def test_invalid_inputs(self, value, expected):
        assert format_decimal(value) == expected


class TestCalculatePercentageChange:
    @pytest.mark.parametrize(
        "old_val,new_val,expected",
        [
            (100, 110, Decimal("10.00")),
            (100, 90, Decimal("-10.00")),
            (50, 75, Decimal("50.00")),
            (0, 100, Decimal("0")),
            (200, 150, Decimal("-25.00")),
        ],
    )
    def test_percentage_change(self, old_val, new_val, expected):
        assert calculate_percentage_change(old_val, new_val) == expected

    def test_no_change(self):
        assert calculate_percentage_change(100, 100) == Decimal("0.00")

    def test_string_inputs(self):
        assert calculate_percentage_change("100", "110") == Decimal("10.00")

    def test_zero_old_value(self):
        assert calculate_percentage_change(0, 100) == Decimal("0")

    def test_invalid_inputs(self):
        assert calculate_percentage_change(None, 100) == Decimal("0")
        assert calculate_percentage_change("abc", 100) == Decimal("0")


class TestValidateTradingPair:
    @pytest.mark.parametrize(
        "pair,expected",
        [
            ("BTC/USDT", True),
            ("ETH/BTC", True),
            ("SOL/USDC", True),
            ("btc/usdt", False),
            ("BTCUSDT", False),
            ("BTC/", False),
            ("/USDT", False),
            ("", False),
            (None, False),
            ("123/USDT", False),
            ("BTC/USDT/EXTRA", False),
        ],
    )
    def test_validate_trading_pair(self, pair, expected):
        assert validate_trading_pair(pair) is expected


class TestParseFloat:
    @pytest.mark.parametrize(
        "value,default,expected",
        [
            ("123.45", 0.0, 123.45),
            ("abc", 0.0, 0.0),
            ("abc", 5.0, 5.0),
            (None, 0.0, 0.0),
            (42, 0.0, 42.0),
            ("-3.14", 0.0, -3.14),
        ],
    )
    def test_parse_float(self, value, default, expected):
        assert parse_float(value, default) == pytest.approx(expected)


class TestParseDecimal:
    @pytest.mark.parametrize(
        "value,default,expected",
        [
            ("123.45", "0", Decimal("123.45")),
            ("abc", "0", Decimal("0")),
            ("abc", "10.5", Decimal("10.5")),
            (None, "0", Decimal("0")),
            (42, "0", Decimal("42")),
        ],
    )
    def test_parse_decimal(self, value, default, expected):
        assert parse_decimal(value, default) == expected


class TestGetTimeframeMinutes:
    @pytest.mark.parametrize(
        "timeframe,expected",
        [
            ("1m", 1),
            ("5m", 5),
            ("15m", 15),
            ("30m", 30),
            ("1h", 60),
            ("4h", 240),
            ("1d", 1440),
            ("1w", 10080),
            ("1M", 1),
            ("UNKNOWN", 1),
            ("", 1),
        ],
    )
    def test_timeframe_mapping(self, timeframe, expected):
        assert get_timeframe_minutes(timeframe) == expected


class TestRoundToNearest:
    @pytest.mark.parametrize(
        "value,nearest,expected",
        [
            (1.234, 0.01, 1.23),
            (1.235, 0.01, 1.24),
            (10.0, 0.5, 10.0),
            (10.7, 0.5, 10.5),
            (10.8, 0.5, 11.0),
            (5.0, 1.0, 5.0),
            (None, 0.01, 0.0),
        ],
    )
    def test_round_to_nearest(self, value, nearest, expected):
        assert round_to_nearest(value, nearest) == pytest.approx(expected)


class TestCalculateGridLevels:
    def test_basic_grid(self):
        levels = calculate_grid_levels(100, 2, 5)
        assert len(levels) == 5
        assert levels == [90.0, 95.0, 100.0, 105.0, 110.0]

    def test_single_level(self):
        levels = calculate_grid_levels(100, 1, 10)
        assert len(levels) == 3
        assert levels == [90.0, 100.0, 110.0]

    def test_zero_levels(self):
        levels = calculate_grid_levels(100, 0, 5)
        assert len(levels) == 1
        assert levels == [100.0]

    def test_invalid_inputs(self):
        assert calculate_grid_levels(None, 2, 5) == []
        assert calculate_grid_levels("abc", 2, 5) == []
        assert calculate_grid_levels(100, "abc", 5) == []


class TestCalculateMartingaleLevels:
    def test_default_multiplier(self):
        levels = calculate_martingale_levels(10, 3)
        assert levels == [10.0, 20.0, 40.0, 80.0]

    def test_custom_multiplier(self):
        levels = calculate_martingale_levels(100, 2, 3.0)
        assert levels == [100.0, 300.0, 900.0]

    def test_single_level(self):
        levels = calculate_martingale_levels(50, 0)
        assert levels == [50.0]

    def test_invalid_inputs(self):
        assert calculate_martingale_levels(None, 3) == []
        assert calculate_martingale_levels("abc", 3) == []
        assert calculate_martingale_levels(10, "abc") == []


class TestValidateDepositAmount:
    def test_valid_amount(self):
        valid, msg = validate_deposit_amount(100, min_amount=10, max_amount=1000)
        assert valid is True
        assert msg == "Valid amount"

    def test_below_minimum(self):
        valid, msg = validate_deposit_amount(5, min_amount=10)
        assert valid is False
        assert "Minimum" in msg

    def test_above_maximum(self):
        valid, msg = validate_deposit_amount(5000, max_amount=1000)
        assert valid is False
        assert "Maximum" in msg

    def test_no_limits(self):
        valid, msg = validate_deposit_amount(123.45)
        assert valid is True

    def test_invalid_input(self):
        valid, msg = validate_deposit_amount("abc")
        assert valid is False
        assert "Invalid" in msg

    def test_decimal_string_input(self):
        valid, msg = validate_deposit_amount("250.50", min_amount="100")
        assert valid is True


class TestFormatCurrency:
    @pytest.mark.parametrize(
        "amount,currency,expected",
        [
            (123.456, "USDT", "123.45 USDT"),
            (0, "USDT", "0.00 USDT"),
            (1.23456789, "BTC", "1.23456789 BTC"),
            (0.0001, "ETH", "0.00010000 ETH"),
            (1000, "USDT", "1000.00 USDT"),
        ],
    )
    def test_format_currency(self, amount, currency, expected):
        assert format_currency(amount, currency) == expected

    def test_invalid_amount(self):
        assert format_currency("abc", "USDT") == "0.00 USDT"

    def test_default_usdt(self):
        assert format_currency(99.99) == "99.99 USDT"


class TestValidateExchangeCredentials:
    def test_valid_credentials(self):
        valid, msg = validate_exchange_credentials(
            "binance", "api-key-min-10-chars", "secret-key-min-10-chars"
        )
        assert valid is True

    def test_missing_exchange_name(self):
        valid, msg = validate_exchange_credentials("", "key12345678", "secret12345678")
        assert valid is False
        assert "Missing" in msg

    def test_missing_api_key(self):
        valid, msg = validate_exchange_credentials("binance", "", "secret12345678")
        assert valid is False

    def test_missing_secret(self):
        valid, msg = validate_exchange_credentials("binance", "key12345678", "")
        assert valid is False

    def test_short_api_key(self):
        valid, msg = validate_exchange_credentials("binance", "short", "secret12345678")
        assert valid is False
        assert "Invalid" in msg

    def test_short_secret_key(self):
        valid, msg = validate_exchange_credentials("binance", "api-key-min-10-chars", "short")
        assert valid is False

    def test_coinbase_requires_passphrase(self):
        valid, msg = validate_exchange_credentials(
            "coinbase", "api-key-min-10-chars", "secret12345678"
        )
        assert valid is False
        assert "Passphrase" in msg

    def test_kraken_requires_passphrase(self):
        valid, msg = validate_exchange_credentials(
            "kraken", "api-key-min-10-chars", "secret12345678"
        )
        assert valid is False

    def test_coinbase_with_passphrase(self):
        valid, msg = validate_exchange_credentials(
            "coinbase", "api-key-min-10-chars", "secret12345678", passphrase="my-passphrase"
        )
        assert valid is True

    def test_kraken_with_passphrase(self):
        valid, msg = validate_exchange_credentials(
            "KRAKEN", "api-key-min-10-chars", "secret12345678", passphrase="my-passphrase"
        )
        assert valid is True

    def test_binance_with_passphrase(self):
        valid, msg = validate_exchange_credentials(
            "binance", "api-key-min-10-chars", "secret12345678", passphrase="ignored"
        )
        assert valid is True


class TestSaveUploadedFile:
    @patch("core.utils.default_storage")
    @patch("core.utils.timezone")
    def test_save_uploaded_file(self, mock_tz, mock_storage):
        mock_tz.now().strftime.return_value = "2026/06/14"
        mock_file = MagicMock()
        mock_file.name = "test_file.txt"
        mock_storage.save.return_value = "uploads/2026/06/14/uuid_test_file.txt"

        result = save_uploaded_file(mock_file, subfolder="uploads")

        assert result == "uploads/2026/06/14/uuid_test_file.txt"
        mock_storage.save.assert_called_once()

    @patch("core.utils.default_storage")
    def test_save_uploaded_file_error(self, mock_storage):
        mock_storage.save.side_effect = Exception("Storage error")
        mock_file = MagicMock()
        mock_file.name = "test.txt"
        with pytest.raises(Exception):
            save_uploaded_file(mock_file)

    def test_save_uploaded_file_default_subfolder(self):
        pass


class TestDeleteFile:
    @patch("core.utils.default_storage")
    def test_delete_existing_file(self, mock_storage):
        mock_storage.exists.return_value = True
        result = delete_file("/path/to/file.txt")
        assert result is True
        mock_storage.delete.assert_called_once_with("/path/to/file.txt")

    @patch("core.utils.default_storage")
    def test_delete_nonexistent_file(self, mock_storage):
        mock_storage.exists.return_value = False
        result = delete_file("/path/to/file.txt")
        assert result is False
        mock_storage.delete.assert_not_called()

    @patch("core.utils.default_storage")
    def test_delete_file_error(self, mock_storage):
        mock_storage.exists.side_effect = Exception("Storage error")
        result = delete_file("/path/to/file.txt")
        assert result is False


class TestCalculateRiskMetrics:
    def test_empty_trades(self):
        result = calculate_risk_metrics([])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["sharpe_ratio"] == 0.0

    def test_none_input(self):
        result = calculate_risk_metrics(None)
        assert result["total_trades"] == 0

    def test_all_winning_trades(self):
        trades = [
            {"profit_loss": 100},
            {"profit_loss": 200},
            {"profit_loss": 50},
        ]
        result = calculate_risk_metrics(trades)
        assert result["total_trades"] == 3
        assert result["winning_trades"] == 3
        assert result["losing_trades"] == 0
        assert result["total_profit_loss"] == 350.0

    def test_all_losing_trades(self):
        trades = [
            {"profit_loss": -100},
            {"profit_loss": -50},
        ]
        result = calculate_risk_metrics(trades)
        assert result["winning_trades"] == 0
        assert result["losing_trades"] == 2
        assert result["win_rate"] == 0.0

    def test_mixed_trades(self):
        trades = [
            {"profit_loss": 100},
            {"profit_loss": -50},
            {"profit_loss": 50},
            {"profit_loss": -20},
        ]
        result = calculate_risk_metrics(trades)
        assert result["total_trades"] == 4
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 2
        assert result["win_rate"] == 50.0

    def test_max_drawdown(self):
        trades = [
            {"profit_loss": 100},
            {"profit_loss": -50},
            {"profit_loss": -30},
            {"profit_loss": 200},
        ]
        result = calculate_risk_metrics(trades)
        assert result["max_drawdown"] > 0

    def test_sharpe_ratio(self):
        trades = [
            {"profit_loss": 100},
            {"profit_loss": -50},
            {"profit_loss": 75},
        ]
        result = calculate_risk_metrics(trades)
        assert isinstance(result["sharpe_ratio"], float)

    def test_single_trade(self):
        trades = [{"profit_loss": 100}]
        result = calculate_risk_metrics(trades)
        assert result["total_trades"] == 1
        assert result["max_drawdown"] == 0.0


class TestGetUtcTimestamp:
    def test_returns_int(self):
        ts = get_utc_timestamp()
        assert isinstance(ts, int)

    def test_recent_timestamp(self):
        import time

        ts = get_utc_timestamp()
        now = int(time.time())
        assert abs(ts - now) < 5


class TestTimestampToDatetime:
    def test_valid_timestamp(self):
        from datetime import datetime

        dt = timestamp_to_datetime(1686729600)
        assert isinstance(dt, datetime)
        assert dt.year == 2023

    def test_invalid_timestamp(self):
        from datetime import datetime

        dt = timestamp_to_datetime("invalid")
        assert isinstance(dt, datetime)


class TestJsonifyDecimal:
    def test_decimal_conversion(self):
        result = jsonify_decimal(Decimal("10.50"))
        assert result == "10.50"

    def test_dict_with_decimals(self):
        result = jsonify_decimal({"price": Decimal("100.50"), "amount": 5})
        assert result == {"price": "100.50", "amount": 5}

    def test_list_with_decimals(self):
        result = jsonify_decimal([Decimal("1.1"), Decimal("2.2"), 3])
        assert result == ["1.1", "2.2", 3]

    def test_nested_structure(self):
        result = jsonify_decimal({"a": {"b": Decimal("99.99")}})
        assert result == {"a": {"b": "99.99"}}

    def test_non_decimal(self):
        result = jsonify_decimal("hello")
        assert result == "hello"


class TestGetClientIP:
    def test_x_forwarded_for(self):
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": "203.0.113.1, 10.0.0.1"}
        assert get_client_ip(request) == "203.0.113.1"

    def test_remote_addr(self):
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        assert get_client_ip(request) == "192.168.1.1"

    def test_x_forwarded_for_preferred(self):
        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "203.0.113.5, 198.51.100.2",
            "REMOTE_ADDR": "192.168.1.1",
        }
        assert get_client_ip(request) == "203.0.113.5"
