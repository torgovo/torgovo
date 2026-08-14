"""
Credential redaction logging filter.

Redacts sensitive credential values (API keys, secrets, passphrases)
from all log messages and traceback output. Applied at the handler
level in Django LOGGING configuration.

This prevents accidental credential leakage through:
- Exception tracebacks (which include all local variables per stack frame)
- Logged config dicts containing decrypted keys
- Accidentally-logged API responses with embedded credentials

Usage:
    'filters': {
        'cred_redact': {
            '()': 'core.logging_filters.CredentialRedactionFilter',
        },
    },
    'handlers': {
        'console': {
            'filters': ['cred_redact'],
            ...
        },
    },
"""

import logging
import re
import traceback
from typing import Pattern


class CredentialRedactionFilter(logging.Filter):
    """Log filter that redacts sensitive credential values from all output.

    Handles both:
    - Log message strings (record.msg, record.args)
    - Exception tracebacks (record.exc_info / record.exc_text)

    Applied per-handler so no credential data reaches any log sink.
    """

    SENSITIVE_KEYS: set = {
        "api_key",
        "apiKey",
        "API_KEY",
        "secret_key",
        "secretKey",
        "SECRET_KEY",
        "passphrase",
        "Passphrase",
        "PASSPHRASE",
        "password",
        "Password",
        "PASSWORD",
        "master_api_key",
        "master_secret_key",
        "master_passphrase",
        "fernet_key",
        "FERNET_KEY",
    }

    def __init__(self, replacement: str = "[REDACTED]"):
        super().__init__()
        self._replacement = replacement
        self._patterns: list[Pattern] = self._compile_patterns()

    def _compile_patterns(self) -> list[Pattern]:
        patterns = []
        for key in self.SENSITIVE_KEYS:
            escaped = re.escape(key)
            patterns.append(
                re.compile(
                    rf"""['"]{escaped}['"]\s*[:=]\s*['"][^'"]+['"]""",
                    re.IGNORECASE,
                )
            )
            patterns.append(
                re.compile(
                    rf"""(?:^|(?<=\W)){escaped}\s*=\s*['"][^'"]+['"]""",
                    re.IGNORECASE,
                )
            )
        return patterns

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(str(record.msg))

        if record.args:
            record.args = self._redact_args(record.args)

        if record.exc_info and record.exc_info[0] is not None:
            try:
                formatted = "".join(traceback.format_exception(*record.exc_info))
                record.exc_text = self._redact(formatted)
                record.exc_info = None
            except Exception:
                pass
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True

    def _redact(self, text: str) -> str:
        for pattern in self._patterns:
            text = pattern.sub(
                lambda m: self._replace_match(m),
                text,
            )
        return text

    def _replace_match(self, match: re.Match) -> str:
        full = match.group(0)
        colon_idx = full.find(":")
        eq_idx = full.find("=")
        sep_idx = colon_idx if colon_idx >= 0 else eq_idx
        if sep_idx < 0:
            return full
        key_part = full[:sep_idx].rstrip()
        return f"{key_part}: '{self._replacement}'"

    def _redact_args(self, args):
        if isinstance(args, dict):
            return {
                k: (
                    self._replacement
                    if self._is_credential_key(k) or self._looks_like_credential(v)
                    else v
                )
                for k, v in args.items()
            }
        return tuple(
            self._replacement if isinstance(a, str) and self._looks_like_credential(a) else a
            for a in args
        )

    @staticmethod
    def _is_credential_key(key) -> bool:
        ks = str(key).lower()
        return any(
            sk in ks
            for sk in {
                "api_key",
                "apikey",
                "secret_key",
                "secretkey",
                "passphrase",
                "password",
                "fernet_key",
                "master_api",
                "master_secret",
            }
        )

    @staticmethod
    def _looks_like_credential(value) -> bool:
        if not isinstance(value, str) or len(value) < 16:
            return False
        alpha_num = sum(c.isalnum() for c in value)
        return alpha_num > len(value) * 0.8
