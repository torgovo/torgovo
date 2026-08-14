"""
Custom middleware for Torgovo Crypto Trading Platform
"""

import logging
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps")

# Rate-limit cache key prefix. The counter lives in the shared cache backend
# (Redis db 1 in production via CACHES['default']), so limits are enforced
# atomically across all web/worker processes — unlike a per-process dict.
RATE_LIMIT_CACHE_PREFIX = "ratelimit"
RATE_LIMIT_WINDOW_SECONDS = 60


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all API requests for debugging and monitoring.
    """

    def process_request(self, request):
        """Log incoming requests."""

        # Skip logging for static files and health checks
        if request.path.startswith("/static/") or request.path == "/health/":
            return None

        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())

        # Log request details
        user_info = "Anonymous"
        # Safely access user attribute (might not exist if AuthenticationMiddleware hasn't run yet)
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated"):
            try:
                if user.is_authenticated:
                    user_info = f"User:{user.email}"
            except Exception:
                pass

        logger.info(
            f"[{request.request_id}] {request.method} {request.path} - {user_info}",
            extra={
                "request_id": request.request_id,
                "method": request.method,
                "path": request.path,
                "user": user_info,
                "ip_address": self.get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
            },
        )

        return None

    def process_response(self, request, response):
        """Log response details and timing."""
        if hasattr(request, "start_time"):
            duration = time.time() - request.start_time
            request_id = getattr(request, "request_id", "unknown")

            # Skip logging for static files and health checks
            if request.path.startswith("/static/") or request.path == "/health/":
                return response

            status_info = f"{response.status_code} {response.reason_phrase}"
            if response.status_code >= 400:
                logger.warning(
                    f"[{request_id}] ERROR: {request.method} {request.path} - "
                    f"{status_info} ({duration:.3f}s)",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration": duration,
                    },
                )
            else:
                logger.info(
                    f"[{request_id}] SUCCESS: {request.method} {request.path} - "
                    f"{status_info} ({duration:.3f}s)",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration": duration,
                    },
                )

        return response

    def get_client_ip(self, request):
        """Get the client's IP address."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Middleware to add security headers to responses.
    """

    def process_response(self, request, response):
        """Add security headers."""
        # Skip for static files
        if request.path.startswith("/static/"):
            return response

        # Security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )

        return response


class RateLimitMiddleware(MiddlewareMixin):
    """
    Distributed rate limiting middleware for API endpoints.

    Request counters live in the shared cache backend (``CACHES['default']``,
    which points at Redis db 1 in production), so limits are enforced
    atomically and consistently across all web/worker processes — unlike a
    per-process in-memory dict that resets on restart and is bypassable by
    spreading requests across workers.

    If the cache backend is unreachable (e.g. a Redis outage), the middleware
    degrades gracefully to an in-process dict so the API keeps serving while
    still enforcing per-process limits.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limits = {}
        super().__init__(get_response)

    def process_request(self, request):
        """Check rate limits."""
        # Only apply to API endpoints
        if not request.path.startswith("/api/"):
            return None

        # Get client identifier
        client_id = self.get_client_id(request)

        # Get current time window (1 minute)
        current_time = int(time.time() // RATE_LIMIT_WINDOW_SECONDS)
        key = f"{client_id}:{current_time}"
        cache_key = f"{RATE_LIMIT_CACHE_PREFIX}:{key}"

        # Get rate limit based on user subscription
        rate_limit = self.get_rate_limit(request)

        # Increment counter atomically via the shared cache backend (Redis).
        try:
            count = cache.incr(cache_key)
        except ValueError:
            # Key does not exist yet: first request in this window. cache.add
            # is atomic (SET NX EX), so concurrent workers only create it once.
            if cache.add(cache_key, 1, timeout=RATE_LIMIT_WINDOW_SECONDS):
                count = 1
            else:
                # Lost the creation race — another worker created the key,
                # so safely increment what is already there.
                count = cache.incr(cache_key)
        except Exception:
            # Cache backend unavailable (Redis down): fall back to the
            # in-process dict so the API never 500s on rate limiting.
            count = self._increment_memory(key, current_time)

        # Check if rate limit exceeded
        if count > rate_limit:
            logger.warning(
                f"Rate limit exceeded for {client_id}: {count}/{rate_limit}",
                extra={"client_id": client_id, "limit": rate_limit},
            )
            return JsonResponse(
                {
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please try again later.",
                    },
                    "timestamp": time.time(),
                },
                status=429,
            )

        # Add rate limit headers
        request.rate_limit_remaining = max(0, rate_limit - count)
        request.rate_limit_total = rate_limit

        return None

    def _increment_memory(self, key, current_time):
        """Increment the counter in the in-process fallback dict."""
        self.cleanup_old_entries(current_time)

        if key not in self.rate_limits:
            self.rate_limits[key] = 0
        self.rate_limits[key] += 1

        return self.rate_limits[key]

    def process_response(self, request, response):
        """Add rate limit headers to response."""
        if hasattr(request, "rate_limit_remaining"):
            response["X-RateLimit-Remaining"] = str(request.rate_limit_remaining)
            response["X-RateLimit-Limit"] = str(request.rate_limit_total)

        return response

    def get_client_id(self, request):
        """Get client identifier for rate limiting."""
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated"):
            try:
                if user.is_authenticated:
                    return f"user:{user.id}"
            except Exception:
                pass

        # Use IP address for anonymous users
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return f"ip:{ip}"

    def get_rate_limit(self, request):
        """Get rate limit based on user subscription."""
        user = getattr(request, "user", None)
        if user and hasattr(user, "is_authenticated"):
            try:
                if user.is_authenticated:
                    if user.is_staff or user.is_superuser:
                        return 5000  # Admin: 5000 requests per minute

                    if user.subscription_plan == "premium":
                        return 1000  # Premium: 1000 requests per minute
                    elif user.subscription_plan == "enterprise":
                        return 3000  # Enterprise: 3000 requests per minute
            except Exception:
                pass

        return 100  # Default: 100 requests per minute

    def cleanup_old_entries(self, current_time):
        """Remove old rate limit entries."""
        keys_to_remove = []
        for key in self.rate_limits:
            try:
                entry_time = int(key.split(":")[-1])
                if current_time - entry_time > 5:  # Keep last 5 minutes
                    keys_to_remove.append(key)
            except Exception:
                pass

        for key in keys_to_remove:
            del self.rate_limits[key]


class RequestBodyLimitMiddleware(MiddlewareMixin):
    """
    Middleware to limit request body size (default 1 MB).

    Webhook endpoints can receive large payloads, but we cap them to
    prevent memory exhaustion attacks.  The limit can be overridden per
    view via ``request._body_limit`` (set in ``process_view`` if needed).
    """

    DEFAULT_BODY_LIMIT = 1_048_576  # 1 MB

    def process_request(self, request):
        content_length = request.META.get("CONTENT_LENGTH")
        if content_length:
            try:
                if int(content_length) > self.DEFAULT_BODY_LIMIT:
                    return JsonResponse(
                        {
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "Request body exceeds size limit",
                            }
                        },
                        status=413,
                    )
            except (ValueError, TypeError):
                pass


class CorrelationIDMiddleware(MiddlewareMixin):
    """
    Middleware to add correlation ID to requests for tracing.
    """

    def process_request(self, request):
        """Add correlation ID to request (reuses existing if set by earlier middleware)."""
        if hasattr(request, "correlation_id"):
            return
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        request.correlation_id = correlation_id

    def process_response(self, request, response):
        """Add correlation ID to response headers."""
        if hasattr(request, "correlation_id"):
            response["X-Correlation-ID"] = request.correlation_id

        return response
