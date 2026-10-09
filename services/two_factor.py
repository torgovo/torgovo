"""
Two-factor authentication (TOTP - RFC 6238) code store/verify service.

Implements Time-based One-Time Passwords using the strongest available
built-in primitives:

  * Secrets are CSPRNG-generated (``secrets``) 20-byte values, base32-encoded
    for display in authenticator apps.
  * Codes are computed per RFC 6238 (HMAC-SHA1 over a 30-second time step)
    and verified with ``hmac.compare_digest`` (constant-time) across a small
    forward/backward clock-drift window.
  * Secrets are stored Fernet-encrypted at rest on ``CustomUser.totp_secret``
    via the shared crypto helpers in ``core.utils`` (never plaintext).

This is the real "code store/verify" layer the withdrawal 2FA gate was
missing: instead of only checking code *presence*, withdrawal requests are
verified against the user's stored TOTP secret.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from core.utils import decrypt_api_key, encrypt_api_key

TOTP_TIME_STEP = 30
TOTP_DIGITS = 6
TOTP_ISSUER = "Torgovo2"


def generate_totp_secret():
    """
    Generate a new TOTP base32 secret (CSPRNG, 160-bit).

    Returns a padded base32 string suitable for both storing (after
    encryption) and rendering in authenticator apps.
    """
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii")


def build_otpauth_uri(secret, account_name):
    """
    Build an ``otpauth://`` provisioning URI for authenticator apps.
    """
    import urllib.parse

    label = "{}:{}".format(TOTP_ISSUER, account_name)
    params = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": TOTP_ISSUER,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_TIME_STEP,
        }
    )
    return "otpauth://totp/{}?{}".format(urllib.parse.quote(label, safe=""), params)


def encrypt_totp_secret(secret):
    """Fernet-encrypt a TOTP secret for at-rest storage."""
    return encrypt_api_key(secret)


def decrypt_totp_secret(stored_value):
    """
    Fernet-decrypt a stored TOTP secret.

    Returns the plaintext secret, or None on empty/invalid input (the
    caller treats None as "2FA not fully provisioned" rather than raising).
    """
    if not stored_value:
        return None
    try:
        return decrypt_api_key(stored_value)
    except Exception:
        return None


def _totp_code(secret_b32, counter, digits=TOTP_DIGITS):
    """
    Compute the RFC 6238 OTP for a specific time-step counter.

    Standard dynamic-truncation of HMAC-SHA1; result is zero-padded to
    ``digits``. Kept private: time handling lives in ``verify_totp_code``.
    """
    key = base64.b32decode(secret_b32.upper().rstrip("=").ljust(8, "="))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp_code(secret_b32, code, window=1, now=None):
    """
    Constant-time verification of ``code`` against ``secret_b32``.

    * ``window`` — +/- number of 30-second steps to accept (clock drift).
    * ``now`` — injectable epoch time for deterministic tests.
    * Uses ``hmac.compare_digest`` so timing does not leak which step matched.

    Returns True only if the code matches the current (or drifted) step.
    """
    if not code:
        return False
    candidate = str(code).strip()
    current = int(now) if now is not None else int(time.time())
    counter = current // TOTP_TIME_STEP
    for offset in range(-window, window + 1):
        expected = _totp_code(secret_b32, counter + offset)
        if hmac.compare_digest(candidate, expected):
            return True
    return False
