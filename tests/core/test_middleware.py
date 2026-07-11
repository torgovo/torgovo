import time
import uuid
from unittest.mock import patch, MagicMock

import pytest
from django.test import RequestFactory
from django.http import HttpResponse, JsonResponse

from core.middleware import (
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    CorrelationIDMiddleware,
)


class TestRequestLoggingMiddleware:
    @pytest.fixture
    def middleware(self):
        return RequestLoggingMiddleware(get_response=lambda req: HttpResponse("ok"))

    def test_sets_start_time_and_request_id(self, middleware):
        request = RequestFactory().get("/api/test/")
        middleware.process_request(request)
        assert hasattr(request, "start_time")
        assert hasattr(request, "request_id")
        assert isinstance(request.request_id, str)
        uuid.UUID(request.request_id)

    def test_skips_static_files(self, middleware):
        request = RequestFactory().get("/static/css/style.css")
        result = middleware.process_request(request)
        assert result is None
        assert not hasattr(request, "start_time")

    def test_skips_health_check(self, middleware):
        request = RequestFactory().get("/health/")
        result = middleware.process_request(request)
        assert result is None

    @patch("core.middleware.logger")
    def test_logs_request_info(self, mock_logger, middleware):
        request = RequestFactory().get("/api/bots/")
        middleware.process_request(request)
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        assert "GET" in args[0]
        assert "/api/bots/" in args[0]

    @patch("core.middleware.logger")
    def test_logs_authenticated_user(self, mock_logger, middleware):
        user = MagicMock()
        user.is_authenticated = True
        user.email = "user@example.com"
        request = RequestFactory().get("/api/bots/")
        request.user = user
        middleware.process_request(request)
        args, kwargs = mock_logger.info.call_args
        assert "user@example.com" in args[0]

    @patch("core.middleware.logger")
    def test_logs_anonymous_user(self, mock_logger, middleware):
        request = RequestFactory().get("/api/bots/")
        middleware.process_request(request)
        args, kwargs = mock_logger.info.call_args
        assert "Anonymous" in args[0]

    def test_process_response_returns_response(self, middleware):
        request = RequestFactory().get("/api/test/")
        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert result is response

    def test_process_response_without_start_time(self, middleware):
        request = RequestFactory().get("/api/test/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert result is response

    @patch("core.middleware.logger")
    def test_logs_success_response(self, mock_logger, middleware):
        request = RequestFactory().get("/api/bots/")
        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())
        response = HttpResponse("ok", status=200)
        middleware.process_response(request, response)
        mock_logger.info.assert_called_once()

    @patch("core.middleware.logger")
    def test_logs_error_response(self, mock_logger, middleware):
        request = RequestFactory().get("/api/bots/")
        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())
        response = HttpResponse("error", status=500)
        middleware.process_response(request, response)
        mock_logger.warning.assert_called_once()

    def test_get_client_ip_x_forwarded(self, middleware):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="203.0.113.1, 10.0.0.1")
        ip = middleware.get_client_ip(request)
        assert ip == "203.0.113.1"

    def test_get_client_ip_remote_addr(self, middleware):
        request = RequestFactory().get("/", REMOTE_ADDR="192.168.1.1")
        ip = middleware.get_client_ip(request)
        assert ip == "192.168.1.1"


class TestSecurityHeadersMiddleware:
    @pytest.fixture
    def middleware(self):
        return SecurityHeadersMiddleware(get_response=lambda req: HttpResponse("ok"))

    def test_adds_security_headers(self, middleware):
        request = RequestFactory().get("/api/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert result["X-Content-Type-Options"] == "nosniff"
        assert result["X-Frame-Options"] == "DENY"
        assert result["X-XSS-Protection"] == "1; mode=block"
        assert result["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_skips_static_files(self, middleware):
        request = RequestFactory().get("/static/js/app.js")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "X-Content-Type-Options" not in result

    @patch("django.conf.settings.DEBUG", False)
    def test_adds_hsts_in_production(self, middleware):
        request = RequestFactory().get("/api/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "Strict-Transport-Security" in result
        assert "max-age=31536000" in result["Strict-Transport-Security"]

    @patch("django.conf.settings.DEBUG", True)
    def test_skips_hsts_in_debug(self, middleware):
        request = RequestFactory().get("/api/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "Strict-Transport-Security" not in result

    @patch("django.conf.settings.DEBUG", False)
    def test_adds_csp_in_production(self, middleware):
        request = RequestFactory().get("/api/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "Content-Security-Policy" in result
        assert "default-src 'self'" in result["Content-Security-Policy"]


class TestRateLimitMiddleware:
    @pytest.fixture
    def middleware(self):
        mw = RateLimitMiddleware(get_response=lambda req: HttpResponse("ok"))
        mw.rate_limits = {}
        return mw

    def test_skips_non_api_routes(self, middleware):
        request = RequestFactory().get("/health/")
        result = middleware.process_request(request)
        assert result is None

    def test_allows_request_within_limit(self, middleware):
        request = RequestFactory().get("/api/bots/")
        result = middleware.process_request(request)
        assert result is None
        assert hasattr(request, "rate_limit_remaining")
        assert hasattr(request, "rate_limit_total")

    def test_rate_limit_exceeded(self, middleware):
        client_id = "ip:127.0.0.1"
        current_time = int(time.time() // 60)
        key = f"{client_id}:{current_time}"
        middleware.rate_limits[key] = 100

        request = RequestFactory().get("/api/bots/", REMOTE_ADDR="127.0.0.1")
        result = middleware.process_request(request)
        assert isinstance(result, JsonResponse)
        assert result.status_code == 429

    def test_adds_rate_limit_headers(self, middleware):
        request = RequestFactory().get("/api/bots/")
        middleware.process_request(request)
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "X-RateLimit-Remaining" in result
        assert "X-RateLimit-Limit" in result

    def test_skips_headers_when_no_rate_limit(self, middleware):
        request = RequestFactory().get("/api/bots/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "X-RateLimit-Remaining" not in result

    def test_rate_limit_headers_values(self, middleware):
        request = RequestFactory().get("/api/bots/")
        middleware.process_request(request)
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        remaining = int(result["X-RateLimit-Remaining"])
        limit = int(result["X-RateLimit-Limit"])
        assert limit == 100
        assert remaining <= limit

    def test_authenticated_user_client_id(self, middleware):
        user = MagicMock()
        user.is_authenticated = True
        user.id = 42
        request = RequestFactory().get("/api/bots/")
        request.user = user
        middleware.process_request(request)
        client_id = middleware.get_client_id(request)
        assert client_id == "user:42"

    def test_anonymous_client_id(self, middleware):
        request = RequestFactory().get("/api/bots/", REMOTE_ADDR="10.0.0.5")
        client_id = middleware.get_client_id(request)
        assert client_id == "ip:10.0.0.5"

    def test_admin_rate_limit(self, middleware):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = True
        user.is_superuser = True
        request = RequestFactory().get("/api/bots/")
        request.user = user
        limit = middleware.get_rate_limit(request)
        assert limit == 5000


class TestCorrelationIDMiddleware:
    @pytest.fixture
    def middleware(self):
        return CorrelationIDMiddleware(get_response=lambda req: HttpResponse("ok"))

    def test_generates_correlation_id(self, middleware):
        request = RequestFactory().get("/api/test/")
        middleware.process_request(request)
        assert hasattr(request, "correlation_id")
        assert isinstance(request.correlation_id, str)
        uuid.UUID(request.correlation_id)

    def test_uses_existing_correlation_id(self, middleware):
        request = RequestFactory().get(
            "/api/test/", HTTP_X_CORRELATION_ID="existing-correlation-id"
        )
        middleware.process_request(request)
        assert request.correlation_id == "existing-correlation-id"

    def test_adds_correlation_to_response(self, middleware):
        request = RequestFactory().get("/api/test/")
        middleware.process_request(request)
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert result["X-Correlation-ID"] == request.correlation_id

    def test_skips_response_without_correlation(self, middleware):
        request = RequestFactory().get("/api/test/")
        response = HttpResponse("ok")
        result = middleware.process_response(request, response)
        assert "X-Correlation-ID" not in result
