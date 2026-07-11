from unittest.mock import MagicMock, patch

import pytest
from django.http import Http404
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    MethodNotAllowed,
    NotAcceptable,
    UnsupportedMediaType,
    Throttled,
    ValidationError as DRFValidationError,
)

from core.exceptions import (
    custom_exception_handler,
    get_error_code,
    get_error_message,
    get_error_details,
    get_status_code,
    get_timestamp,
    TradingBotException,
    ExchangeAPIException,
    InsufficientBalanceException,
    InvalidOrderException,
    BotLimitException,
    QuantumAIDepositException,
    WebhookException,
)


class TestCustomExceptionClasses:
    def test_trading_bot_exception_defaults(self):
        exc = TradingBotException("Something went wrong")
        assert exc.message == "Something went wrong"
        assert exc.error_code == "TRADING_BOT_ERROR"
        assert exc.status_code == 400

    def test_trading_bot_exception_custom(self):
        exc = TradingBotException("Custom error", error_code="CUSTOM_CODE", status_code=418)
        assert exc.message == "Custom error"
        assert exc.error_code == "CUSTOM_CODE"
        assert exc.status_code == 418

    def test_exchange_api_exception(self):
        exc = ExchangeAPIException("Exchange down", exchange_name="binance")
        assert exc.message == "Exchange down"
        assert exc.error_code == "EXCHANGE_API_ERROR"
        assert exc.status_code == 503
        assert exc.exchange_name == "binance"

    def test_exchange_api_exception_no_exchange(self):
        exc = ExchangeAPIException("Generic exchange error")
        assert exc.exchange_name is None

    def test_insufficient_balance_exception(self):
        exc = InsufficientBalanceException("Low balance", required_balance=1000)
        assert exc.message == "Low balance"
        assert exc.error_code == "INSUFFICIENT_BALANCE"
        assert exc.status_code == 402
        assert exc.required_balance == 1000

    def test_insufficient_balance_no_balance(self):
        exc = InsufficientBalanceException("Low balance")
        assert exc.required_balance is None

    def test_invalid_order_exception(self):
        exc = InvalidOrderException("Invalid order params")
        assert exc.message == "Invalid order params"
        assert exc.error_code == "INVALID_ORDER"
        assert exc.status_code == 400

    def test_bot_limit_exception(self):
        exc = BotLimitException("Too many bots", current_bots=10, max_bots=3)
        assert exc.message == "Too many bots"
        assert exc.error_code == "BOT_LIMIT_EXCEEDED"
        assert exc.status_code == 429
        assert exc.current_bots == 10
        assert exc.max_bots == 3

    def test_bot_limit_exception_defaults(self):
        exc = BotLimitException("Limit reached")
        assert exc.current_bots is None
        assert exc.max_bots is None

    def test_quantum_ai_deposit_exception(self):
        exc = QuantumAIDepositException("Deposit failed", deposit_amount=500.0)
        assert exc.message == "Deposit failed"
        assert exc.error_code == "DEPOSIT_ERROR"
        assert exc.status_code == 400
        assert exc.deposit_amount == 500.0

    def test_quantum_ai_deposit_exception_defaults(self):
        exc = QuantumAIDepositException("Failed")
        assert exc.deposit_amount is None

    def test_webhook_exception(self):
        exc = WebhookException("Webhook processing error", webhook_id="wh_12345")
        assert exc.message == "Webhook processing error"
        assert exc.error_code == "WEBHOOK_ERROR"
        assert exc.status_code == 400
        assert exc.webhook_id == "wh_12345"

    def test_webhook_exception_defaults(self):
        exc = WebhookException("Error")
        assert exc.webhook_id is None

    def test_exception_string_representation(self):
        exc = TradingBotException("test message")
        assert str(exc) == "test message"

    def test_inheritance_chain(self):
        assert issubclass(ExchangeAPIException, TradingBotException)
        assert issubclass(InsufficientBalanceException, TradingBotException)
        assert issubclass(InvalidOrderException, TradingBotException)
        assert issubclass(BotLimitException, TradingBotException)
        assert issubclass(QuantumAIDepositException, TradingBotException)
        assert issubclass(WebhookException, TradingBotException)


class TestGetErrorCode:
    @pytest.mark.parametrize(
        "exception,expected",
        [
            (AuthenticationFailed(), "AUTHENTICATION_FAILED"),
            (NotAuthenticated(), "AUTHENTICATION_REQUIRED"),
            (NotFound(), "RESOURCE_NOT_FOUND"),
            (ParseError(), "PARSE_ERROR"),
            (MethodNotAllowed("GET"), "METHOD_NOT_ALLOWED"),
            (NotAcceptable(), "NOT_ACCEPTABLE"),
            (UnsupportedMediaType("application/xml"), "UNSUPPORTED_MEDIA_TYPE"),
            (Throttled(), "RATE_LIMIT_EXCEEDED"),
            (Http404(), "RESOURCE_NOT_FOUND"),
            (DRFValidationError("err"), "VALIDATION_ERROR"),
        ],
    )
    def test_known_codes(self, exception, expected):
        assert get_error_code(exception) == expected

    def test_unknown_exception(self):
        exc = ValueError("something")
        assert get_error_code(exc) == "INTERNAL_SERVER_ERROR"

    def test_trading_bot_exception(self):
        exc = TradingBotException("error")
        assert get_error_code(exc) == "INTERNAL_SERVER_ERROR"


class TestGetErrorMessage:
    def test_from_detail_string(self):
        exc = DRFValidationError("This field is required.")
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "This field is required."

    def test_from_detail_list(self):
        exc = DRFValidationError(["Error one", "Error two"])
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "Error one"

    def test_from_detail_dict_with_non_field_errors(self):
        exc = DRFValidationError({"non_field_errors": ["Global error"]})
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "Global error"

    def test_from_detail_dict_field_errors(self):
        exc = DRFValidationError({"field": ["Field error"]})
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "Validation failed. Please check your input."

    def test_http404(self):
        exc = Http404()
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "The requested resource was not found."

    def test_permission_denied_django(self):
        exc = PermissionDenied()
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "You do not have permission to perform this action."

    def test_django_validation_error(self):
        exc = DjangoValidationError("Invalid input")
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert str(exc) == str(exc)
        assert msg == str(exc)

    @patch("django.conf.settings.DEBUG", True)
    def test_debug_mode_returns_str(self):
        exc = ValueError("Debug error message")
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "Debug error message"

    @patch("django.conf.settings.DEBUG", False)
    def test_production_mode_default_message(self):
        exc = ValueError("Internal error")
        context = MagicMock()
        msg = get_error_message(exc, context)
        assert msg == "An internal server error occurred. Please try again later."


class TestGetErrorDetails:
    def test_no_detail(self):
        exc = ValueError("no detail attr")
        assert get_error_details(exc) is None

    def test_detail_dict(self):
        exc = DRFValidationError({"field": ["error"]})
        details = get_error_details(exc)
        assert details == {"field": ["error"]}

    def test_detail_list(self):
        exc = DRFValidationError(["error1", "error2"])
        details = get_error_details(exc)
        assert details == ["error1", "error2"]

    def test_detail_string(self):
        exc = AuthenticationFailed("bad credentials")
        details = get_error_details(exc)
        assert details == {"detail": "bad credentials"}


class TestGetStatusCode:
    @pytest.mark.parametrize(
        "exception,expected",
        [
            (AuthenticationFailed(), status.HTTP_401_UNAUTHORIZED),
            (NotAuthenticated(), status.HTTP_401_UNAUTHORIZED),
            (NotFound(), status.HTTP_404_NOT_FOUND),
            (ParseError(), status.HTTP_400_BAD_REQUEST),
            (MethodNotAllowed("GET"), status.HTTP_405_METHOD_NOT_ALLOWED),
            (NotAcceptable(), status.HTTP_406_NOT_ACCEPTABLE),
            (UnsupportedMediaType("xml"), status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
            (Throttled(), status.HTTP_429_TOO_MANY_REQUESTS),
            (Http404(), status.HTTP_404_NOT_FOUND),
            (DRFValidationError("err"), status.HTTP_400_BAD_REQUEST),
        ],
    )
    def test_known_status_codes(self, exception, expected):
        assert get_status_code(exception) == expected

    def test_unknown_exception(self):
        exc = ValueError("something")
        assert get_status_code(exc) == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetTimestamp:
    def test_returns_isoformat_string(self):
        ts = get_timestamp()
        assert isinstance(ts, str)
        assert "T" in ts
        assert ts.endswith("+00:00") or ts.endswith("Z") or "+" in ts


class TestCustomExceptionHandler:
    def _make_context(self, method="GET", path="/api/test/", user=None):
        request = MagicMock()
        request.method = method
        request.path = path
        request.user = user or MagicMock()
        request.user.is_authenticated = False
        view = MagicMock()
        view.__class__.__name__ = "TestView"
        return {"request": request, "view": view}

    def test_handler_returns_response_for_drf_exception(self):
        exc = NotFound()
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        assert response is not None
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data
        assert response.data["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "timestamp" in response.data

    def test_handler_returns_none_for_non_drf_exception(self):
        exc = ValueError("random")
        context = self._make_context()
        result = custom_exception_handler(exc, context)
        assert result is None

    def test_handler_includes_field_errors_for_dict_detail(self):
        exc = DRFValidationError({"email": ["This field is required."], "password": ["Too short."]})
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        assert response is not None
        assert "field_errors" in response.data["error"]
        assert response.data["error"]["field_errors"]["email"] == ["This field is required."]

    @patch("django.conf.settings.DEBUG", True)
    def test_handler_includes_debug_info(self):
        exc = NotFound()
        context = self._make_context(method="POST", path="/api/bots/")
        response = custom_exception_handler(exc, context)
        assert "debug" in response.data
        assert response.data["debug"]["request_method"] == "POST"
        assert response.data["debug"]["request_path"] == "/api/bots/"
        assert response.data["debug"]["view_class"] == "TestView"

    @patch("django.conf.settings.DEBUG", False)
    def test_handler_omits_debug_info_in_production(self):
        exc = NotFound()
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        assert "debug" not in response.data

    def test_status_code_override(self):
        class CustomDRFException(NotFound):
            pass

        exc = CustomDRFException()
        context = self._make_context()
        response = custom_exception_handler(exc, context)
        assert response.status_code == status.HTTP_404_NOT_FOUND
