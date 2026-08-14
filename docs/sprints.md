# Sprint Cadence & Velocity

> Lightweight 2-week sprint process for a small/single-contributor team. Adopted
> 2026-08-13 to close the PM-audit gap ("no sprint cadence, estimation, or velocity").

## Rhythm

| Event | When | Output |
|-------|------|--------|
| Sprint planning | Sprint start (every 2nd Monday) | Goals + issue list, sized S/M/L |
| Async standup | Mon/Thu (see `COMMS.md`) | Yesterday / Today / Blockers |
| Sprint review | Sprint end (every 2nd Friday) | What shipped, demo, issues closed |
| Retrospective | End of sprint review | 1 keep / 1 stop / 1 start |
| Risk + register refresh | End of sprint | `risk-register.md` updated |

## Sizing

- **S** — ≤ half a day · **M** — ≤ 2 days · **L** — ≤ 1 week
- Any single issue > 1 week must be split before it enters a sprint.

## Tracking

- Issues live in GitHub Issues with labels: `bug`, `feature`, `chore`, `security`,
  plus severity `sev:critical|high|medium|low`.
- Milestones = sprints (`2026-S3`, `2026-S4`, ...).
- Every issue in a sprint gets an estimate; velocity = points (S=1, M=3, L=5)
  delivered per sprint, recorded in the sprint review section below.

## Sprint Log

| Sprint | Dates | Planned | Delivered | Velocity | Notes |
|--------|-------|---------|-----------|----------|-------|
| 2026-S1 | baseline (2026-08-13) | — | — | — | PM audit fixes: commit-msg hook, LICENSE/CONTRIBUTING, risk register, doc consolidation, v0.1.0 baseline |

> After the first full sprint, fill in each row at the review meeting.
