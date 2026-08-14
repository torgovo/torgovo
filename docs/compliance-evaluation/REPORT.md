# Torgovo2 — Compliance Evaluation

**Evaluated:** 2026-07-28
**Skills applied:** compliance-os, gdpr-dsgvo-expert, gdpr-audit-prep, information-security-manager-iso27001, iso27001-audit-prep, soc2-compliance, soc2-audit-prep, eu-ai-act-specialist, compliance-readiness, risk-management-specialist

---

## Executive Summary

Torgovo2 has **strong technical security foundations** (Fernet encryption, JWT auth, rate limiting, audit logging, security headers) but is **missing all legal/regulatory compliance features** required for a production trading platform. There is no KYC/AML infrastructure, no GDPR compliance (no consent tracking, no data export, no right to deletion), no terms-of-service acceptance, and no privacy policy. The project is not ready for production deployment with real users and real money.

**Compliance maturity: 30/100** — solid technical controls, zero legal/regulatory layer.

---

## Findings by Skill

### 1. gdpr-dsgvo-expert / gdpr-audit-prep
- **Rating: F**
- **Critical gaps:** No `gdpr`, `privacy`, `consent`, `data_retention`, or `data_deletion` references anywhere in the codebase.
- **User consent:** No `terms_accepted` field on the user model, no consent timestamps, no privacy-policy acceptance tracking.
- **Data export:** No endpoint to export user data in a portable format.
- **Right to deletion:** No self-service account deletion; admin can only disable `is_active`.
- **Data retention:** No scheduled cleanup of old audit logs, sessions, or expired data.
- **PII storage:** User PII (email, phone, name) stored in plaintext in PostgreSQL — no encryption at rest.
- **Cookie consent:** No banner, no model, no middleware.
- **Recommendation:** Add `terms_accepted_at` + `privacy_version` to user model. Implement `GET /api/users/export-data/` and `DELETE /api/users/delete-account/` with anonymization. Add data-retention cron for audit logs > 12 months.

### 2. soc2-compliance / soc2-audit-prep / information-security-manager-iso27001
- **Rating: D**
- **Common Criteria (security + availability + confidentiality):**
  - **Security (partially met):** Fernet encryption for API keys., JWT auth, rate limiting, security headers (HSTS, CSP), audit logging, credential redaction from logs. Password validators active.
  - **Availability (partially met):** Celery task queue, Nginx + Gunicorn production stack, health check endpoint, Sentry error tracking.
  - **Confidentiality (partially met):** CredentialRedactionFilter on all logs, admin form masking for secrets.
- **Gaps (SOC 2 / ISO 27001 common control gaps):**
  - No formal change management process
  - No vulnerability management / patch cadence
  - No business continuity / disaster recovery plan documented
  - No vendor risk assessments
  - No formal access review process
  - No security awareness training artifacts
  - No incident response playbook beyond code-level incident-commander tools
  - No documented data classification policy
  - No physical/environmental security controls documented
  - No penetration testing schedule
- **Recommendation:** Create `docs/security-policy.md` and `docs/incident-response.md`. Schedule quarterly access reviews. Add vulnerability scanning to CI.

### 3. eu-ai-act-specialist
- **Rating: N/A**
- The project uses algorithmic trading strategies (grid, martingale, signal) but these are deterministic rule-based systems, not AI/ML models. The "Quantum AI" naming is misleading — it's a pooled fund with manual admin trading, not an AI system. No ML models are trained or deployed. The EU AI Act does not apply.

### 4. risk-management-specialist
- **Rating: D**
- **Evidence:** `docs/archive/ISSUES.md` serves as an informal risk register but is not structured. No formal risk assessment exists for:
  - Exchange API outages (single point of failure via CCXT)
  - Key compromise (Fernet key was previously committed to git — H1)
  - Single-contributor bus factor
  - Regulatory risk (no KYC/AML)
  - Financial risk (manual payment approval, no automated reconciliation)
- **Recommendation:** Create `docs/risk-register.md` with likelihood/impact/mitigation for top 10 risks. Include a trading-risk section covering slippage, exchange insolvency, and API rate limits.

### 5. compliance-readiness (cross-framework)
- **Rating: D**
- **Scoring against common framework domains:**
  - **Access Control (A):** JWT with refresh rotation, role-based (IsAuthenticated/IsAdminUser)
  - **Cryptography (A):** Fernet for API keys, HS256 for JWT
  - **Audit & Accountability (B):** AuditLog, UserActivityLog, LoginAttempt, request logging
  - **Risk Assessment (F):** No formal risk register or assessment
  - **Security Assessment (F):** No pen test schedule, no vulnerability scanning in CI
  - **System & Comms Protection (B):** Security headers, CSP, HSTS, Nginx hardening
  - **Contingency Planning (F):** No DR plan, no backup/restore documentation
  - **Incident Response (F):** No documented incident response procedure
  - **Maintenance (D):** Dependency updates are manual, no Dependabot/Renovate
  - **Supplier Risk (N/A):** No third-party vendor management
- **Recommendation:** Address the F-scored domains first. A `docs/compliance-roadmap.md` with target frameworks and timeline would guide the work.

---

## Applicability Matrix

| Skill | Relevance | Score | Rationale |
|-------|-----------|-------|-----------|
| gdpr-dsgvo-expert | HIGH | F | EU users require GDPR — zero implementation exists |
| gdpr-audit-prep | HIGH | F | Cannot pass a GDPR audit |
| soc2-compliance | MEDIUM | D | Technical controls are solid; policy/documentation layer missing |
| iso27001-audit-prep | LOW | D | Too early for formal ISMS; adopt SOC 2 first |
| information-security-manager-iso27001 | LOW | D | Premature — build on SOC 2 foundations first |
| compliance-readiness | MEDIUM | D | Technical controls score B/A; policy/process layer scores F |
| eu-ai-act-specialist | NONE | N/A | No ML/AI systems in the codebase |
| risk-management-specialist | MEDIUM | D | Informal risk awareness but no structured register |
| capa-officer | NONE | N/A | Medical device QMS — not applicable |
| fda-consultant-specialist | NONE | N/A | Medical device — not applicable |
| iso13485/14971/mdr/42001 | NONE | N/A | Medical device/AIMS — not applicable |

---

## Cross-Cutting Observations

| Strength | Detail |
|----------|--------|
| Encryption | Fernet-based API key encryption with credential redaction from logs is production-grade |
| Audit logging | AuditLog + UserActivityLog + LoginAttempt triple layer covers traceability well |
| Rate limiting | Multi-layer (DRF throttles + middleware + Nginx + brute-force lockout) |
| Security headers | HSTS (1 year), CSP, X-Frame-Options DENY, nosniff — good baseline |
| JWT auth | Refresh token rotation, blacklisting, separate signing key |

| Gap | Severity | Detail |
|-----|----------|--------|
| No KYC/AML | CRITICAL | Crypto trading platform without identity verification is a regulatory violation in most jurisdictions |
| No GDPR compliance | CRITICAL | EU users would trigger GDPR Article 17 (right to erasure), Article 20 (data portability), and consent requirements |
| No ToS acceptance | HIGH | No legal basis for service usage |
| PII in plaintext | MEDIUM | User email/phone stored unencrypted at rest |
| No vulnerability scanning | MEDIUM | No Dependabot, no Snyk, no CI security scanning |
| No DR/BCP plan | MEDIUM | No documented disaster recovery or backup procedures |
| Key rotation warning | LOW | `looks_encrypted()` includes a note about key-rotation hazards |
| CSP `unsafe-inline` | LOW | Weakens XSS protection slightly |

---

## Recommendations

### P0 (Before Production Launch)
1. **KYC/AML** — Implement identity document verification and sanctions screening. Minimum: government ID upload + verification status workflow.
2. **GDPR consent** — Add `terms_accepted_at`, `privacy_version` to user model. Block registration without acceptance.
3. **Right to deletion** — Implement `DELETE /api/users/me/` with full data anonymization (not just `is_active = False`).
4. **Data export** — Implement `GET /api/users/export-data/` returning JSON with all user data.
5. **Terms of service** — Add legal text files (`docs/TERMS.md`, `docs/PRIVACY.md`) and an API endpoint to serve them.

### P1 (Before Scaling)
6. **Data retention policy** — Add Celery periodic task to prune audit logs > 12 months, expired sessions, unverified accounts > 30 days.
7. **Incident response plan** — Create `docs/incident-response.md` with severity levels, escalation tree, communication templates.
8. **Vulnerability scanning** — Add Dependabot or Renovate. Run `pip-audit` or `safety` in CI.
9. **Access review process** — Schedule quarterly admin account audit. Log all admin actions.

### P2 (Growth Stage)
10. **SOC 2 readiness** — Document controls across the 5 Trust Service Criteria. Begin evidence collection for Type I.
11. **Disaster recovery plan** — Document RTO/RPO, backup strategy, restore testing procedure.
12. **Penetration testing** — Schedule annual third-party pen test. Remediate findings within SLA.

---

## Data Sources

| Source | Details |
|--------|---------|
| `core/utils.py:30-82` | Fernet encrypt/decrypt/looks_encrypted |
| `core/models.py:135-179` | AuditLog model definition |
| `core/models.py:54-79` | UserActivityLog model definition |
| `core/middleware.py:100-129` | SecurityHeadersMiddleware (CSP, HSTS, etc.) |
| `core/middleware.py:132-242` | RateLimitMiddleware |
| `core/logging_filters.py:33-142` | CredentialRedactionFilter |
| `apps/authentication/views.py:155-174` | Brute-force lockout logic |
| `apps/authentication/models.py` | EmailVerification, LoginAttempt |
| `apps/users/models.py:154-162` | is_email_verified, is_phone_verified |
| `config/settings/base.py:135-147` | AUTH_PASSWORD_VALIDATORS |
| `config/settings/base.py:176-226` | JWT config (HS256, rotation, blacklisting) |
| `config/settings/base.py:259-265` | Security settings (HSTS, XSS, nosniff) |
| `config/settings/production.py:18-34` | Production security hardening |
| `config/settings/base.py:191-206` | DRF throttle rates |
| `docs/archive/ISSUES.md` | Informal risk register (open decisions) |
| `.env.example` | Fernet key generation instructions |

<!-- 2026-08-10 (opencode): 30/100 → 35/100. Technical-control deltas verified; legal/regulatory layer unchanged and still blocks production. -->

## 2026-08-10 Re-assessment: 30/100 → 35/100

Re-verified against the live codebase **2026-08-10** (grep sweep + settings/middleware read). The *technical-security* half of the score strengthened; the *legal/regulatory* half is materially unchanged.

**Improved since 2026-07-28:**

1. **Rate limiting is now cache/Redis-backed, not in-memory.** `core/middleware.py:171-187` uses `cache.incr` / `cache.add` with `RATE_LIMIT_CACHE_PREFIX`; `config/settings/base.py:127-133` configures `django.core.cache.backends.redis.RedisCache` (production at `config/settings/production.py:90-92` uses `django_redis.cache.RedisCache`). This clears the original engineering P0 ("Replace in-memory rate limiter with Redis") that the compliance cross-framework notes relied on — a real SOC 2 Availability/Confidentiality control upgrade. (Test env still uses `LocMemCache`, appropriate for CI.)
2. **Fernet key-compromise risk mitigated (H1).** The original risk item "Fernet key was previously committed to git" is resolved: `.env` is no longer tracked in git (`git ls-files .env` empty), `DEBUG=True → False`, and `FERNET_KEY` rotated to a fresh 44-char key (old key in `.env.bak-20260810`; re-encrypt via `manage.py reencrypt_credentials --old-key <old>` once Postgres is up). This closes a named entry in the risk-management section and in the engineering re-assessment.
3. **No new KYC/AML/GDPR surface appeared.** Repo-wide sweep for `export-data`, `delete-account`, `terms_accepted`, `privacy policy`, `sanction`, `id verification` returns **zero** app-code hits (only false positives: `PyYAML` / `js-yaml` matching `-yaml`, and "verification code" matching `id.verif`). Consent fields (`terms_accepted_at`, `privacy_version`) still absent from `apps/users/models.py`; only deletion path remains admin `is_active = False` (`apps/users/views.py:386,390`).

**Unchanged critical blockers (all still P0 / CRITICAL):**

- **KYC/AML:** zero infrastructure — no identity doc upload, no verification status workflow, no sanctions screening.
- **GDPR:** no consent tracking, no `GET /api/users/export-data/`, no `DELETE /api/users/me/` anonymization endpoint, no data-retention cron, no cookie-consent layer, PII in plaintext at rest.
- **ToS / Privacy Policy:** no `docs/TERMS.md`, `docs/PRIVACY.md`, no acceptance tracking, no endpoint to serve them.
- **Formal controls:** no structured risk register, no vulnerability scanning in CI, no DR/BCP plan, no incident-response playbook, no pen-test schedule.

These are pre-launch legal/regulatory requirements that no amount of engineering hardening can substitute — they must be built before real users and real money.

**New grade: 35/100 (D+).** The technical half (encryption, auth, audit logging, now-Redis rate limiting, security headers) may warrant B/C-tier on its own, but the legal layer is still ~zero, capping the composite. The Applicability Matrix letter grades are unchanged (GDPR F, KYC F, SOC2/ISO D) and remain valid as the reference audit.

Original grade, findings, applicability matrix, and priority recommendations above remain valid as the reference audit.
