# Security Evaluation — Torgovo2 (8th Domain)

**Date:** 2026-08-15 (live code re-check)
**Scope:** `/mnt/data/Projects/torgovo2` — Django REST API, auth, secrets, webhooks, payments, bots, config, dependencies
**Method:** Read-only OWASP/pen-test recon. No code changes made (audit report only). Skills: `security-pen-testing`, `security-reviewer`, `env-secrets-manager`.
**Graded:** **C (Conditional)** — security baseline is solid but has one privilege-escalation path, one password(-less) fraud gap, and stale prod dependencies.

---

## 1. Executive Summary

Torgovo2 has a genuinely strong security baseline: CSPRNG email tokens, locked-down JWT config, constant-time webhook auth with replay protection, `DEBUG=False` + full HTTPS hardening in production settings, `.env` untracked, Fernet-encrypted exchange credentials, strict account-based QuerySet scoping, and rate limiting on register/login/password-reset/webhooks/withdrawals.

Five real issues were confirmed that prevent a higher grade:

| # | Severity | Finding | CWE / Ref |
|---|----------|---------|-----------|
| S-1 | **HIGH** | Privilege escalation via `UserDetailView` mass assignment — `subscription_plan`, `is_subscription_active`, `max_bots_allowed`, `referral_code`, trade-stats writable by self-PATCH | CWE-269, CWE-915 |
| S-2 | **MED** | Phone OTP generated with `random.choices` (non-CSPRNG) + stored plaintext + non-constant-time compare; `send_verification_sms` comment falsely claims hashed storage | CWE-331, CWE-338, CWE-307 | **FIXED (2026-08-16)** |
| S-3 | **MED** | Withdrawal 2FA gate validates presence/length of code but never verifies it against any store — any authenticated 2FA-enabled user can request a withdrawal with a bogus code | CWE-287 | **FIXED (2026-08-15)** |
| S-4 | **MED** | Gunicorn `==21.2.0` pinned but vulnerable to TE.CL / conflicting Transfer-Encoding request smuggling (fix `22.0.0`) | PYSEC-2026-1433/1434 |
| S-5 | **MED** | sentry-sdk `==1.38.0` leaks env vars to subprocesses when `env={}` used (fix `1.45.1`/`2.8.0`) | PYSEC-2026-1917 |

Minor issues (all FIXED): dev-only vulnerable pins (pytest, black) — bumped 2026-08-16; no throttle on phone-verification request endpoint — `phone_verification` scope added; stale `.backup` source file with dead `two_factor_secret` field — deleted.

---

## 2. Findings Detail

### S-1 (HIGH) — Privilege escalation through `UserDetailView` mass assignment
- **Where:** `apps/authentication/views.py:271-279` (`UserDetailView(RetrieveUpdateAPIView)`, `get_object()` returns `request.user`); `apps/authentication/serializers.py:122-153` (`UserSerializer`).
- **What:** `UserSerializer.Meta.fields` include `subscription_plan`, `is_subscription_active`, `max_bots_allowed`, `referral_code`, `total_trades_executed`, `total_volume_traded`. `read_only_fields` only covers `id`, `is_email_verified`, `is_phone_verified`, `date_joined`, `last_login`, `two_factor_enabled`.
- **Exploit:** authenticated `PATCH /api/auth/user/` with `{"subscription_plan": "premium", "is_subscription_active": true}`. `CustomUser.save()` (`apps/users/models.py:193-201`) recomputes `max_bots_allowed = get_plan_limit(plan)` → 25 (or 100 for enterprise). `has_active_subscription()` (`:247-254`) then returns `True` (plan != free, active flag True, end-date None). User now has premium limits with no payment; can also inflate `total_trades_executed`/`total_volume_traded` and swap `referral_code`.
- **Mitigation:** mark these fields `read_only` (or move plan/status behind an admin-only serializer); derive trade stats from `update_trading_stats()` instead of accepting client writes.

### S-2 (MED) — OTP: non-CSPRNG generation, plaintext storage, weak compare, false comment
- **Where:** `apps/authentication/signals.py:17-19` (`generate_otp_code`, `import random` at :6); `apps/authentication/models.py:52-67` (`PhoneVerification.code = CharField(max_length=6)`, plaintext); `apps/authentication/serializers.py:231` (`verification.code != code`, non-constant-time); `apps/authentication/views.py:396-398` (`send_verification_sms` comment: "The code is stored hashed in DB" — **false**, contradicts `models.py:56`).
- **Exploit:** OTPs drawn from Mersenne Twister (`random.choices(string.digits)`) are short-term predictable if an attacker can seed/sample the generator; plaintext storage + `!=` gives a timing side-channel and exposes the code to anyone who reads the DB (e.g., a leaked pg_dump). Attempts are capped (`max_attempts`, `:232-236`) which lowers practical brute-force risk but does not fix the core weaknesses.
- **Mitigation:** use `secrets.choice`; hash the code or compare constant-time (`hmac.compare_digest`); fix the misleading comment.

**RESOLVED 2026-08-16** — CSPRNG + hash-at-rest + constant-time verify:
- `generate_otp_code` uses `secrets.choice` (`signals.py`); confirm compare is `check_password` (`serializers.py` — constant-time against the stored hash), replacing the plaintext `!=`/`hmac.compare_digest` compare.
- `PhoneVerificationSerializer.create` now stores `make_password(code)` (salted PBKDF2) instead of the raw 6-digit value; `models.py` `code = CharField(max_length=128)` (migration `authentication.0004`). The raw code is attached only transiently (`verification.raw_code`, in-memory, never persisted/logged) as a seam for a future real SMS send.
- `send_verification_sms` comment corrected: the code is now a salted hash at rest; logs still must never echo it.
- Tests: `test_create_verification` asserts stored value is a hash (`check_password(raw, pv.code)`); all confirm fixtures use `make_password("123456")`. Full suite green.

### S-3 (MED) — Withdrawal 2FA gate is a presence check, not verification
- **Where:** `apps/payments/views.py:244-279` (`WithdrawalRequestViewSet.perform_create` — comment itself says "The actual TOTP/SMS check should live in a dedicated service; here we at least enforce presence and length").
- **What:** rejects only when `two_factor_code` missing / `<4` chars, or when `user.two_factor_enabled is False`. The code is never matched against a stored token, OTP, or TOTP value anywhere in the codebase.
- **Exploit:** any authenticated user with 2FA enabled (or who can self-flip `two_factor_enabled`? no — read_only — but 2FA-enabled accounts generally) can submit `two_factor_code="0000"` and create a withdrawal. Note: `WithdrawalRequestSerializer` still validates amount ≥ min, address length, blockchain allowlist, and ≤3 concurrent pending (good), and status is server-set to `pending` with admin approval — so a wrong code cannot move funds alone; it is a broken control-in-depth link.
- **Mitigation:** verify the code against `PhoneVerification` (unused, matching `is_verified=False`) or a TOTP secret (field was removed from the live model); or drop the gate and document that real 2FA lands with a proper TOTP service.

**RESOLVED 2026-08-15** — real TOTP 2FA is now implemented and the gate verifies against it:
- New `services/two_factor.py`: RFC 6238 TOTP code store/verify (CSPRNG 20-byte secrets, constant-time `hmac.compare_digest`, ±1 step drift window, Fernet-encrypted at rest via `core.utils`). `CustomUser.totp_secret` added (migration `users.0005`).
- `WithdrawalRequestViewSet.perform_create` now decrypts the stored secret and requires a **verifiable** code (`verify_totp_code`, window=1); bogus codes return 400. The raw code is popped from `validated_data` so it is never persisted.
- Self-service endpoints under `/api/auth/2fa/`: `setup/` (provisions + returns secret/otpauth URI), `confirm/` (enables only after a valid generated code), `disable/` (requires password **and** valid code, then wipes the secret). All throttled (`two_factor: 5/hour`).
- Tests: `tests/authentication/test_two_factor.py` (17) + expanded withdrawal gate tests in `tests/payments/test_views.py`. Full suite green (see Verification section).

### S-4 (MED) — Gunicorn 21.2.0 pinned to a request-smuggling release
- **Where:** `requirements/production.txt:4` (`gunicorn==21.2.0`), also `base.txt:69` (`gunicorn>=21.2.0`).
- **What:** PYSEC-2026-1433 (TE.CL smuggling via unvalidated `Transfer-Encoding`) and PYSEC-2026-1434 (conflicting TE headers treated as chunked) — both fixed in `22.0.0`. Realistic only when a network path doesn't strip invalid requests; still a DSO-grade upgrade.
- **Mitigation:** bump to `==22.0.0` in both files.

### S-5 (MED) — sentry-sdk 1.38.0 env leak
- **Where:** `requirements/production.txt:8-9` (`sentry-sdk[django]==1.38.0`).
- **What:** PYSEC-2026-1917 — Stdlib integration passes all env vars to subprocesses even when `env={}` given; API keys like `BINANCE_API_KEY` etc. could leak to child processes. Fixed `1.45.1`/`2.8.0`.
- **Mitigation:** bump to `==1.45.1` (minor, safe) or `2.8.0+`.

### S-6 (LOW) — Dev-only vulnerable pins
- `pytest 7.4.3` (PYSEC-2026-1845 → 9.0.3), `black 23.11.0` (PYSEC-2024-48 → 24.3.0; PYSEC-2026-2120/2121 → 26.3.0/26.3.1) in `requirements/development.txt`. Dev environment only; upgrade at leisure.

**RESOLVED 2026-08-16** — pinned to current venv-verified versions in `requirements/development.txt`: `pytest==9.1.0`, `pytest-django==4.12.0`, `pytest-asyncio==1.4.0`, `pytest-cov==4.1.0`, `pytest-mock==3.15.1`, `black==26.3.1`. Full suite + `manage.py check` re-run green against these pins.

### S-7 (LOW) — No throttle on phone-verification request
- `PhoneVerificationRequestView` (`apps/authentication/views.py:381`) has no `throttle_scope` (unlike register/login/password_reset). An authenticated user can trigger unlimited `send_verification_sms` calls → SMS-spam / carrier cost (SMS is a no-op stub today, so cost is theoretical but the throttle gap is real).

### S-8 (INFO) — Dead artifact: `apps/authentication/models.py.backup`
- Contains stale `two_factor_enabled`/`two_factor_secret` line (`:36-37`) and duplicates the live model. Remove from repo to avoid confusion and stale-code greps. (And note: no live TOTP/django-otp implementation exists anywhere despite the `two_factor_enabled` flag.)

---

## 3. Verified Strengths (passing checks)

- **Auth tokens / JWT** (`config/settings/base.py:218-232`): access 15m, refresh 7d, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`, `SIMPLE_JWT_SIGNING_KEY` separate from `DJANGO_SECRET_KEY`.
- **Email verification** (`apps/authentication/models.py:13-49`, `views.py:282-380`): token via `core/utils.py:26-30` `secrets.token_urlsafe(64)` (CSPRNG), 24h expiry, prior tokens invalidated, unverified registration gets tokens returned anyway (accepted design — no post-registration feature gate).
- **Login lockout** (`views.py:53+`): `LoginAttempt` records normalized email, per-IP-prefix + UA-prefix grouping (UA-2), thresholded lockout, `throttle_scope="login"` (20/hr).
- **Webhooks** (`apps/webhooks/views.py:110-266`): dual auth — HMAC header **and** body-secret paths, both via `hmac.compare_digest` (constant-time); replay protection via `cache.add(dedupe_key, "1", TIMESTAMP_MAX_AGE)` + fallback hash of `bot_id|ts|side|pair|position_size`; `_record_failure(bot_id, ip)` on bad creds; timestamp parsing with 1e12–2e12 sanity range; `throttle_scope="webhook"` (120/min).
- **Production settings** (`config/settings/production.py`): `DEBUG=False`, `SECURE_SSL_REDIRECT`, session/CSRF cookies `Secure`+`HttpOnly`+`Samesite=Lax`, HSTS 31536000 + includeSubDomains + preload, `SECURE_REFERRER_POLICY`, `SECURE_PROXY_SSL_HEADER`, env-driven `CSRF_TRUSTED_ORIGINS`.
- **Secrets hygiene**: `.env` not tracked in git (`git ls-files .env` empty; `.gitignore:68-71`); `SECRET_KEY`/`JWT_SECRET_KEY`/`FERNET_KEY` env-driven, never hardcoded; previous run rotated FERNET_KEY and flipped `DEBUG=False`.
- **Exchange credentials** (`apps/exchanges/models.py:67,107-120`): `api_key`/`secret_key`/`passphrase` Fernet-encrypted at save with `looks_encrypted` double-write guard; `get_decrypted_credentials()` used only at runtime.
- **Account-scoped data** (`apps/bots/views.py:105-107` etc.): every non-admin ViewSet `get_queryset()` filters `user=self.request.user`; admin-only ViewSets/actions enforce `IsAdminUser` (`apps/users/views.py:35-459`, payments approve/reject, QuantumAIFund).
- **Withdrawals** (`apps/payments/serializers.py:194-240`, `views.py:244-279`): amount > 0 & ≥ `WITHDRAWAL_MIN_AMOUNT`, address ≥10 chars, blockchain allowlist, ≤3 concurrent pending, server-computed network/processing fees, `status='pending'` forced, ≥$1000 auto-flag, admin-only approve/reject.
- **Middleware chain** (`config/settings/base.py`): RequestLogging → RequestBodyLimit → SecurityHeaders → CorrelationID → RateLimit (Redis-backed).
- **Admin surface**: all admin views `[IsAdminUser]`; audit log + login history retained.
- **Dependency baseline** (`pip-audit`): `requirements/base.txt` — 0 known vulns. Prod vulnerabilities are limited to the two pinned apps above (S-4/S-5).

---

## 4. Verification Method & Environment

- Ran against live tree at `main = 2bcfd5b`; `manage.py check` 0 issues; full suite green (1859–1866 passed / 13 skipped — see engineering-evaluation).
- `pip-audit` (installed into project `.venv` only, never system) against `requirements/base.txt` (0), `development.txt` (pytest/black), `production.txt` (gunicorn/sentry-sdk).
- Findings confirmed by direct line reads; no code modified.

## 5. Recommendation Order (DSO-style)

1. **S-1** serializer `read_only` for plan/status/stats → closes the only privilege-escalation path (1-line change each field).
2. **S-4** `gunicorn==22.0.0` + **S-5** `sentry-sdk==1.45.1` (prod deps; verify suite + smoke).
3. **S-3** withdraw-gate: verify code against real store or remove the fake gate.
4. **S-2** `secrets`-based OTP + hash-at-rest + constant-time compare + fix comment.
5. **S-7** add `throttle_scope` to `PhoneVerificationRequestView`.
6. **S-6/S-8** dev-pin bumps + delete `.backup`.

Grade: **C (Conditional)** — closes to B after S-1 + S-4/S-5 land, which are low-risk, well-scoped fixes.

**Post-audit status (2026-08-16): all 8 findings RESOLVED** — see §8 Fix Status. All fixes verified by full suite `1888 passed / 13 skipped`, `manage.py check` 0 issues, flake8 0 findings. Grade now re-assessed per engineering-evaluation process.

*Report authored during live re-check 2026-08-15. Subsequent security sessions: re-run the `pip-audit` commands and re-read S-1/S-2/S-3 code paths before any grade change.*
---

## 8. Fix Status (2026-08-15 post-audit implementation)

| S-ID | Finding | Status |
|------|---------|--------|
| S-1 | `UserSerializer` plan/status/stats mass assignment (HIGH) | **FIXED** — all 6 fields added to `read_only_fields`; regression test `test_billing_and_quota_fields_read_only` |
| S-4 | gunicorn 21.2.0 request smuggling | **FIXED** — `22.0.0` in `requirements/production.txt` |
| S-5 | sentry-sdk 1.38.0 env leak | **FIXED** — `1.45.1` in `requirements/production.txt` |
| S-2 | OTP non-CSPRNG / non-constant-time / false comment / plaintext storage | **FIXED** — `secrets` in `signals.py`; **hash-at-rest**: `make_password` in `PhoneVerificationSerializer.create`, `code` now `CharField(max_length=128)` (migration `authentication.0004`), constant-time `check_password` compare; comment corrected; transient `raw_code` never persisted/logged. Tests: `test_otp_code_generator_csprng_properties` + `test_create_verification` hash assertions |
| S-7 | `PhoneVerificationRequestView` no throttle | **FIXED** — `throttle_scope = "phone_verification"` + `4`/`5`/hour rate in `base.py` |
| S-8 | stale `models.py.backup` | **FIXED** — deleted |
| S-3 | withdrawal 2FA presence-only | **FIXED** — RFC 6238 TOTP service (`services/two_factor.py`) + `CustomUser.totp_secret` (users.0005 + `services.two_factor`); withdrawals require a **verifiable** code; self-service `api/auth/2fa/{setup,confirm,disable}` endpoints (throttled). Tests: `tests/authentication/test_two_factor.py` (17) + `tests/payments/test_views.py` gate cases |
| S-6 | dev pins (pytest 7.4.3, black 23.11.0) | **FIXED** — `requirements/development.txt`: `pytest==9.1.0`, `pytest-django==4.12.0`, `pytest-asyncio==1.4.0`, `pytest-cov==4.1.0`, `pytest-mock==3.15.1`, `black==26.3.1` (PYSEC-2024-48, PYSEC-2026-2120/2121); verified running in project `.venv` |

Verification: `manage.py check` 0 issues; full suite **1888 passed, 13 skipped** (auth+webhooks 189).
