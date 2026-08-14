# Risk Register

> Tracking risk as of 2026-08-13. Update at least once per sprint or when a risk's
> probability/impact changes. Each row: risk, likelihood (L), impact (I), mitigation,
> owner. L/I scale: Low / Med / High.

## Active Risks

| ID | Risk | L | I | Mitigation | Owner |
|----|------|---|---|------------|-------|
| R01 | Exchange API key exposure (live Binance/Bybit keys in `.env`) | Med | High | `.env` untracked + `.gitignore` enforced; keys to be regenerated on each exchange; re-encrypt via `manage.py reencrypt_credentials`; never log secrets | DevOps |
| R02 | Exchange API breaking changes (CCXT/Bybit/Binance) | Med | High | Pin ccxt version; integration tests per exchange; monitor exchange changelogs; rollback plan in `SOPs.md` | Trading |
| R03 | Single-contributor bus factor (all PM knowledge in one head) | High | Med | This risk register; `docs/internal/COMMS.md` decision log; canonical docs in `docs/`; future issues in GitHub tracker | Lead |
| R04 | Bot auto-commits create unreadable git history | High | Low | `commit-msg` hook enforces Conventional Commits; history baseline squashed at `v0.1.0` (optional); PR-based flow | Lead |
| R05 | Doc drift (parallel doc folders) | Med | Med | Single source of truth in `docs/`; `docs/README.md` index; drift dir consolidated 2026-08-13 | Lead |
| R06 | Webhook replay / forged signals | Low | High | Body `secret` (constant-time compare) + optional HMAC `X-Signature`; `timestamp` window `TIMESTAMP_MAX_AGE = 120s` | Security |
| R07 | No sprint cadence → unpredictable delivery | Med | Med | Lightweight 2-week sprints per `docs/sprints.md`; velocity + KPI tracking | Lead |
| R08 | No git tags / semver for deployed versions | Med | Med | `v0.1.0` baseline tag; release process in `SOPs.md`; CHANGELOG linked to versions | Lead |

## Incident Tiering (from `docs/internal/SOPs.md`)

- **SEV1** — platform down / funds at risk → respond ≤ 15 min, run SEV1 runbook.
- **SEV2** — major feature broken, no workaround → respond ≤ 1 hr.
- **SEV3** — minor issue, workaround exists → respond ≤ 24 hr.

## Escalation

1. Fix via `SOPs.md` runbooks. 2. Open an incident thread in `#incidents`.
3. Post-mortem after any SEV1/SEV2. 4. Log the fix + root cause in this register.
