# Product KPIs

> 5 product-health metrics, reviewed weekly (see `COMMS.md` reporting cadence).
> Baselines recorded 2026-08-13. Targets are stretch goals — review quarterly.

| KPI | Definition | Baseline | Target | Owner |
|-----|------------|----------|--------|-------|
| Test coverage | % lines covered by `tests/` (`pytest --cov`) | 89% (Phase-3 measurement, web/backend) | ≥ 90% | QA |
| CI green rate | % of CI runs passing (last 30) | 100% (1949+ passed, 13 skipped) | ≥ 98% | Dev |
| Bot uptime | % of running bots without engine error per week | TBD (first measured week) | ≥ 99% | Trading |
| Trades executed | Total executed trades per week | TBD | Trending up | Product |
| Subscription conversion | Signups → active paid subscriptions % | TBD | ≥ 5% | Marketing |

## Measurement Notes

- Test coverage: `pytest --cov` report at each release, recorded in `docs/CHANGELOG.md`.
- Bot uptime: derived from bot `last_error` / engine heartbeat; first baseline needs a
  full running week before a number is committed.
- Trades + conversions require production data — until a live deployment with users
  exists, record `TBD` rather than inventing numbers.

## Weekly Metrics Message (paste into standup thread)

```
Coverage: <pct>   CI: <green/total>   Uptime: <pct>   Trades: <n>   Conv: <pct>
Drift this week: <what changed vs last week>
```
