"""
FR A2 / Model C plan limits — the single source for bot-creation gates.

Resolution order for a user (``effective_limits``):

  1. **model_c** — an active, non-hard-stopped ``BotSubscription`` whose
     ``BotSubscriptionPlan.subscription_plan`` bridge points at a Model C
     ``SubscriptionPlan`` row (the subscribe flow creates these as
     ``bot_type="custom"`` shims, so that flavour is preferred, then most
     recent). The ``SubscriptionPlan`` row is the authority for
     ``max_bots_allowed`` / ``bot_types`` / ``max_signals_per_month`` —
     everything here is read from the DB, never hard-coded (Q6 matrix is
     admin-editable on the plan row itself).
  2. **legacy** — any other usable BotSubscription (per-bot plans).
     Display-only: legacy create paths keep their historical G4 behaviour
     and are NOT count-gated (see gate wiring in ``apps/bots/views.py``).
  3. **none** — no subscription at all.

Gates (``enforce_bot_creation``) run ONLY for ``source == "model_c"``:

  * **Type gate** — ``bot_type`` must be in ``plan.bot_types``.
    ``quantum_ai`` is always exempt (Q2: quantum is an investment product
    bought as a separate legacy subscription — Model C tiers never grant it).
    Vocabulary note: callers pass Model C names (``signal``/``grid``/
    ``martingale``/``quantum_ai``); ``signal`` maps to the legacy
    ``bot_type="custom"`` shim.
  * **Count gate** — Signal + Grid + Martingale rows (``is_deleted=False``)
    >= ``max_bots_allowed`` → ``BotLimitException`` (429). Same basis as
    ``User.can_create_more_bots`` so frontend gating and the server gate
    can never disagree. QuantumAIBot is deliberately NOT in the sum: it has
    no ``user`` field (FK to the admin-managed QuantumAIFund master fund),
    so its rows are never user-attributable — filtering them by ``user``
    raised FieldError (regression: docs/
    regression-quantum-aibot-seat-count-fielderror.md).

Errors: type gate raises ``PermissionError`` → 403
(``core.exceptions.custom_exception_handler``, same convention as the G4
"No active … subscription" errors); count gate raises
``core.exceptions.BotLimitException`` → 429.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanLimits:
    """Effective entitlements for one user (see module docstring)."""

    source: str  # "model_c" | "legacy" | "none"
    slug: str | None  # Model C plan slug (model_c only)
    max_bots: int  # seat cap (model_c: SubscriptionPlan row; else profile/default)
    bot_types: frozenset | None  # None = unrestricted (legacy/none)
    max_signals_per_month: int | None  # webhook quota (model_c only)
    subscription: object | None = None  # payments.BotSubscription to create bots under


def effective_limits(user) -> PlanLimits:
    """Resolve the user's current entitlements (DB-driven, cheap: 1 query)."""
    from apps.payments.models import BotSubscription
    from apps.payments.services.expiry import is_hard_stopped

    active = (
        BotSubscription.objects.filter(user=user, status="active")
        .select_related("plan", "plan__subscription_plan")
        .order_by("-created_at")
    )
    # Grace rows still count as usable (A6: full access in grace); only
    # hard-stopped rows lose the ability to create new bots.
    usable = [s for s in active if not is_hard_stopped(s)]

    model_c = [s for s in usable if s.plan.subscription_plan_id is not None]
    if model_c:
        # Prefer the "custom" shim the subscribe flow creates (all Model C
        # tiers), else the newest linked row (admin-created bridge).
        sub = next((s for s in model_c if s.plan.bot_type == "custom"), model_c[0])
        plan = sub.plan.subscription_plan
        return PlanLimits(
            source="model_c",
            slug=plan.slug,
            max_bots=plan.max_bots_allowed,
            bot_types=frozenset(plan.bot_types or ()),
            max_signals_per_month=plan.max_signals_per_month,
            subscription=sub,
        )

    if usable:
        # Legacy: per-bot plans — no user-level quota to enforce here; the
        # caller's G4 lookup + historical behaviour stay in charge.
        sub = usable[0]
        features = sub.plan.features if isinstance(sub.plan.features, dict) else {}
        return PlanLimits(
            source="legacy",
            slug=None,
            max_bots=features.get("max_bots") or user.max_bots_allowed,
            bot_types=None,
            max_signals_per_month=None,
            subscription=sub,
        )

    return PlanLimits(
        source="none",
        slug=None,
        max_bots=user.max_bots_allowed,
        bot_types=None,
        max_signals_per_month=None,
        subscription=None,
    )


def count_user_bots(user) -> int:
    """Seat count — identical basis to ``User.can_create_more_bots``.

    QuantumAIBot excluded: no ``user`` field (rows hang off the admin
    QuantumAIFund master fund) — a ``user=`` filter raised FieldError.
    """
    from apps.bots.models import GridBot, MartingaleBot, SignalBot

    return (
        SignalBot.objects.filter(user=user, is_deleted=False).count()
        + GridBot.objects.filter(user=user, is_deleted=False).count()
        + MartingaleBot.objects.filter(user=user, is_deleted=False).count()
    )


def enforce_bot_creation(user, bot_type: str, limits: PlanLimits | None = None) -> PlanLimits:
    """FR A2 gates for creating one bot of ``bot_type``.

    No-op for legacy/none sources (G4 already gates access there —
    never gate twice). Returns the resolved ``limits`` so callers can use
    ``limits.subscription`` as the Model C row to save the bot under.
    """
    from core.exceptions import BotLimitException

    if limits is None:
        limits = effective_limits(user)
    if limits.source != "model_c":
        return limits

    # Type gate (Q2: quantum_ai always exempt — separate legacy purchase).
    if bot_type != "quantum_ai" and bot_type not in limits.bot_types:
        raise PermissionError(f"Your plan does not include {bot_type} bots (plan: {limits.slug})")

    # Count gate — seats across all bot types vs the plan's max_bots_allowed.
    used = count_user_bots(user)
    if used >= limits.max_bots:
        raise BotLimitException(
            f"Bot limit reached for plan '{limits.slug}' ({used}/{limits.max_bots})",
            current_bots=used,
            max_bots=limits.max_bots,
        )
    return limits
