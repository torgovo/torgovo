"""
Request ID logging filter.

Injects the correlation ID (set by CorrelationIDMiddleware) into every
log record so all logs for a single request can be correlated.
"""

import logging


class RequestIDFilter(logging.Filter):
    """Add request_id to each log record from the current thread-local context."""

    _request_id: str = ""

    @classmethod
    def set_request_id(cls, request_id: str):
        cls._request_id = request_id

    @classmethod
    def clear_request_id(cls):
        cls._request_id = ""

    def filter(self, record):
        record.request_id = getattr(record, "request_id", self._request_id) or "-"
        return True
