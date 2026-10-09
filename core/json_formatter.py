"""
Structured JSON logging formatter for production.

Outputs each log line as a single JSON object with standard fields:
timestamp, level, logger, message, request_id, plus any extra fields.

Requires: python-json-logger (already in stdlib via json module).
"""

import json
import logging
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging in production."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        # Add request_id if present (from RequestIDFilter)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Add any extra fields from the logger call
        skip_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "msecs",
            "message",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "request_id",
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in skip_attrs:
                continue
            if key == "exc_info" and value:
                try:
                    log_entry["exception"] = {
                        "type": record.exc_info[0].__name__,
                        "message": str(record.exc_info[1]),
                        "traceback": "".join(traceback.format_exception(*record.exc_info)),
                    }
                except Exception:
                    pass
            elif not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                log_entry[key] = str(value)
            else:
                log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)
