# Regression: BotSubscriptionPlan.bot_type unique constraint dropped

**Date:** 2026-10-16 (documented; change made earlier in the G5 session)
**Area:** `apps/payments/models.py` — `BotSubscriptionPlan.bot_type`
**Severity:** Low (schema intent change, deliberate)

## What broke / failed

`tests/payments/test_models.py::TestBotSubscriptionPlanModel::test_bot_type_unique`
started failing with `DID NOT RAISE Exception`: creating a second
`BotSubscriptionPlan` with the same `bot_type="grid"` no longer raised
`IntegrityError`.

## Root cause

G5 / Model C (FR A2 tier ladder) needs **one "custom" shim plan per Model C
tier** (Free / Basic / Standard / Premium / Creator). With
`unique=True` on `bot_type`, only ONE `custom` plan could exist, so the
per-tier shim design was impossible. The constraint was dropped in the
G5 work (`unique=True` → plain `CharField`, replaced by a non-unique
`Index(fields=["bot_type"])`). The old test asserting uniqueness was left
behind and the referenced regression doc was never written — both fixed
2026-10-16.

## Fix applied

1. `bot_type` stays non-unique (Model C shim-per-tier requirement;
   `bot_type` is only a coarse type discriminator).
2. Test updated: `test_bot_type_not_unique_g5` now asserts a second plan
   with the same `bot_type` is ALLOWED (duplicate grid plan + a second
   `custom` shim both succeed).

## How it was tested

`pytest tests/payments/test_models.py -q` — updated test passes; full
`tests/payments tests/subscriptions tests/referrals` subset green afterwards.

## Lesson

A deliberate schema-constraint change must ship with (a) the regression doc
in the same change and (b) every test that asserts the old constraint
updated/removed in the same change — never leave a test red on the next run.
