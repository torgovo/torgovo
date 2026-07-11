"""
Custom exception handlers for Torgovo Crypto Trading Platform
"""
import logging
import traceback
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import Http404
from django.core.exceptions import PermissionDenied, ValidationError

logger = logging.getLogger('apps')


def custom_exception_handler(exc, context):
    """
    Custom exception handler for REST API.
    """
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Handle custom TradingBotException (DRF default handler returns None for these)
    if response is None and isinstance(exc, TradingBotException):
        response = Response(
            {'error': str(exc.message) if hasattr(exc, 'message') else str(exc)},
            status=getattr(exc, 'status_code', 400),
        )

    # Handle built-in PermissionError (raised by bot view perform_create)
    if response is None and isinstance(exc, PermissionError):
        response = Response(
            {'error': str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Add custom error handling
    if response is not None:
        custom_response_data = {
            'error': {
                'code': get_error_code(exc),
                'message': get_error_message(exc, context),
                'details': get_error_details(exc) if hasattr(exc, 'detail') else None,
            },
            'timestamp': get_timestamp(),
        }

        # Add field-specific errors for validation errors
        if hasattr(exc, 'detail') and isinstance(exc.detail, dict):
            field_errors = {}
            for field, errors in exc.detail.items():
                if isinstance(errors, list):
                    field_errors[field] = errors
                else:
                    field_errors[field] = [str(errors)]

            custom_response_data['error']['field_errors'] = field_errors

        # Add request information for debugging (in development)
        if settings.DEBUG:
            custom_response_data['debug'] = {
                'request_method': context['request'].method,
                'request_path': context['request'].path,
                'view_class': context['view'].__class__.__name__,
                'exception_type': exc.__class__.__name__,
                'traceback': traceback.format_exc() if settings.DEBUG else None,
            }

        response.data = custom_response_data
        response.status_code = get_status_code(exc)

    # Log the exception
    logger.error(
        f"API Exception: {exc.__class__.__name__} - {str(exc)}",
        exc_info=True,
        extra={
            'request_method': context['request'].method,
            'request_path': context['request'].path,
            'user': context['request'].user if context['request'].user.is_authenticated else None,
        }
    )

    return response


def get_error_code(exception):
    """
    Map exception to error code.
    """
    error_codes = {
    'AuthenticationFailed': 'AUTHENTICATION_FAILED',
    'NotAuthenticated': 'AUTHENTICATION_REQUIRED',
    'PermissionDenied': 'PERMISSION_DENIED',
    'PermissionError': 'PERMISSION_DENIED',
    'NotFound': 'RESOURCE_NOT_FOUND',
    'ValidationError': 'VALIDATION_ERROR',
    'ParseError': 'PARSE_ERROR',
    'MethodNotAllowed': 'METHOD_NOT_ALLOWED',
    'NotAcceptable': 'NOT_ACCEPTABLE',
    'UnsupportedMediaType': 'UNSUPPORTED_MEDIA_TYPE',
    'Throttled': 'RATE_LIMIT_EXCEEDED',
    'Http404': 'RESOURCE_NOT_FOUND',
    }

    # Check if the exception has its own error_code attribute (e.g. TradingBotException)
    if hasattr(exception, 'error_code'):
        return exception.error_code
    exception_type = exception.__class__.__name__
    return error_codes.get(exception_type, 'INTERNAL_SERVER_ERROR')


def get_error_message(exception, context):
    """
    Get user-friendly error message.
    """
    if hasattr(exception, 'detail'):
        if isinstance(exception.detail, str):
            return exception.detail
        elif isinstance(exception.detail, dict) and 'non_field_errors' in exception.detail:
            return exception.detail['non_field_errors'][0]
        elif isinstance(exception.detail, list):
            return str(exception.detail[0])
        elif isinstance(exception.detail, dict):
            return 'Validation failed. Please check your input.'

    # Custom messages for specific exceptions
    if isinstance(exception, Http404):
        return 'The requested resource was not found.'

    if isinstance(exception, PermissionDenied):
        return 'You do not have permission to perform this action.'

    if isinstance(exception, ValidationError):
        return str(exception)

    # Exchange API errors
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        if exception.response.status_code == 429:
            return 'Exchange API rate limit exceeded. Please try again later.'
        elif exception.response.status_code >= 500:
            return 'Exchange API is currently unavailable. Please try again later.'

    # Default message
    if settings.DEBUG:
        return str(exception)
    else:
        return 'An internal server error occurred. Please try again later.'


def get_error_details(exception):
    """
    Get detailed error information.
    """
    if hasattr(exception, 'detail'):
        if isinstance(exception.detail, dict):
            return exception.detail
        elif isinstance(exception.detail, list):
            return exception.detail
        else:
            return {'detail': str(exception.detail)}

    return None


def get_status_code(exception):
    """
    Get appropriate HTTP status code.
    """
    status_codes = {
        'AuthenticationFailed': status.HTTP_401_UNAUTHORIZED,
        'NotAuthenticated': status.HTTP_401_UNAUTHORIZED,
        'PermissionDenied': status.HTTP_403_FORBIDDEN,
        'PermissionError': status.HTTP_400_BAD_REQUEST,
        'NotFound': status.HTTP_404_NOT_FOUND,
        'ValidationError': status.HTTP_400_BAD_REQUEST,
        'ParseError': status.HTTP_400_BAD_REQUEST,
        'MethodNotAllowed': status.HTTP_405_METHOD_NOT_ALLOWED,
        'NotAcceptable': status.HTTP_406_NOT_ACCEPTABLE,
        'UnsupportedMediaType': status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        'Throttled': status.HTTP_429_TOO_MANY_REQUESTS,
        'Http404': status.HTTP_404_NOT_FOUND,
    }

    # Check if the exception has its own status_code attribute (e.g. TradingBotException)
    if hasattr(exception, 'status_code'):
        return exception.status_code
    exception_type = exception.__class__.__name__
    return status_codes.get(exception_type, status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_timestamp():
    """
    Get current timestamp.
    """
    from django.utils import timezone
    return timezone.now().isoformat()


# Custom exception classes
class TradingBotException(Exception):
    """Base exception for trading bot errors."""

    def __init__(self, message, error_code=None, status_code=400):
        self.message = message
        self.error_code = error_code or 'TRADING_BOT_ERROR'
        self.status_code = status_code
        super().__init__(self.message)


class ExchangeAPIException(TradingBotException):
    """Exception for exchange API errors."""

    def __init__(self, message, exchange_name=None, status_code=503):
        self.exchange_name = exchange_name
        super().__init__(
            message=message,
            error_code='EXCHANGE_API_ERROR',
            status_code=status_code
        )


class InsufficientBalanceException(TradingBotException):
    """Exception for insufficient balance errors."""

    def __init__(self, message, required_balance=None):
        self.required_balance = required_balance
        super().__init__(
            message=message,
            error_code='INSUFFICIENT_BALANCE',
            status_code=402
        )


class InvalidOrderException(TradingBotException):
    """Exception for invalid order parameters."""

    def __init__(self, message):
        super().__init__(
            message=message,
            error_code='INVALID_ORDER',
            status_code=400
        )


class BotLimitException(TradingBotException):
    """Exception when user exceeds bot limit."""

    def __init__(self, message, current_bots=None, max_bots=None):
        self.current_bots = current_bots
        self.max_bots = max_bots
        super().__init__(
            message=message,
            error_code='BOT_LIMIT_EXCEEDED',
            status_code=429
        )


class QuantumAIDepositException(TradingBotException):
    """Exception for Quantum AI deposit errors."""

    def __init__(self, message, deposit_amount=None):
        self.deposit_amount = deposit_amount
        super().__init__(
            message=message,
            error_code='DEPOSIT_ERROR',
            status_code=400
        )


class WebhookException(TradingBotException):
    """Exception for webhook processing errors."""

    def __init__(self, message, webhook_id=None):
        self.webhook_id = webhook_id
        super().__init__(
            message=message,
            error_code='WEBHOOK_ERROR',
            status_code=400
        )