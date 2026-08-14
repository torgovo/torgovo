# Internal Communications

## Channels

| Channel | Purpose | Retention |
|---------|---------|-----------|
| Slack #engineering | Code review, deploy notifications, tech discussions | 90 days |
| Slack #incidents | SEV1/SEV2 incidents only, real-time debug | 90 days |
| GitHub Issues | Bug tracking, feature requests | Permanent |
| GitHub PRs | Code review, change discussion | Permanent |
| Weekly Standup | Async updates (Slack thread, Mon/Thu) | 90 days |

## Communication Standards

### Commit Messages
```
<type>(<scope>): <short summary>

<optional body — what, why, not how>
```
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`

### PR Template
```
## What
<what changed>

## Why
<why changed>

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] manual check

## Reviewers
@<reviewer>
```

### Incident Notifications
```
SEV<1|2|3>: <brief description>
Impact: <users/exchanges/bots affected>
Status: <detecting/investigating/resolved>
Link: <Sentry issue link>
```

### Standup Format (Slack thread)
```
Yesterday: <completed>
Today: <planned>
Blockers: <if any>
```

## Branch & PR Workflow (adopted 2026-08-13)

- `main` — production, always deployable. Direct pushes blocked; changes land via PR.
- `develop` — integration branch, default target for feature work.
- `feat/<slug>`, `fix/<slug>` — short-lived feature/fix branches off `develop`.
- PR into `main` runs the full CI gate (pre-commit + `manage.py check` + test suite
  with ≥80% coverage floor). PR into `develop` runs a lighter check.
- Merge strategy: squash to `main` to keep history linear and readable.
- Releases: tag `v<major>.<minor>.<patch>` on `main`; version bumped in `CHANGELOG.md`.

## Decision Log

All significant decisions logged in `docs/internal/COMMS.md` (here):

| Date | Decision | Rationale | Author |
|------|----------|-----------|--------|
| 2025-10-28 | Keep legacy `trading/` directory as read-only | Contains historical logic — may need reference | Team |
| 2025-10-30 | Use Celery for bot execution, not Redis Queue | Better monitoring, existing infra | Team |
| 2025-11-01 | Fernet encryption for API keys | Minimal overhead, Django-friendly | Security |
| 2025-11-10 | Django REST Framework over FastAPI | Existing Django ecosystem, ORM integration | Team |

## Reporting Cadence

| Report | Audience | Frequency | Owner |
|--------|----------|-----------|-------|
| Deploy status | Team | Per-deploy | Deployer |
| Incident review | Engineering | Post-SEV1 | IC lead |
| Weekly metrics | Team | Monday | Lead dev |
| Monthly review | + Business | 1st Monday | Team lead |
| Quarterly roadmap | All | Quarterly | Product |
