"""
G2 / FR A3 — payment-code order checks + proof fulfillment.

Mirrors (never modifies) the validation semantics of the legacy endpoints
apps/subscriptions/views.py::TelegramSubscribeView (duplicate 409 with
metadata, max_subscribers capacity 409) and SubscribeView (bot duplicate),
in the same precedence order, so both flows behave identically.

Read side (quotes) lives in apps/payments/services/quote.py.
"""

import logging
from decimal import Decimal

from rest_framework import serializers

from apps.payments.models import BotSubscription, BotSubscriptionPlan, PaymentCode
from apps.subscriptions.models import TelegramSubscription
from core.exceptions import Conflict

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ["expired", "cancelled", "rejected"]


def check_order_allowed(code: PaymentCode) -> None:
    """
    Pre-flight at code CREATION (fail early on duplicate/capacity).
    Also re-run at proof time — capacity may have filled meanwhile.
    """
    user = code.user
    if code.order_kind == "telegram_signal":
        plan = code.telegram_plan
        duplicate = (
            TelegramSubscription.objects.filter(user=user, plan=plan)
            .exclude(status__in=TERMINAL_STATUSES)
            .first()
        )
        if duplicate:
            raise Conflict(
                {
                    "message": "You already have an active or pending subscription to this plan",
                    "subscription_id": str(duplicate.id),
                    "status": duplicate.status,
                }
            )
        if plan.max_subscribers is not None:
            taken = (
                TelegramSubscription.objects.filter(plan=plan)
                .exclude(status__in=TERMINAL_STATUSES)
                .count()
            )
            if taken >= plan.max_subscribers:
                raise Conflict("Plan has reached maximum subscribers")
        return

    # bot kind — duplicate is per resolved BotSubscriptionPlan (get_or_create
    # keyed exactly like legacy SubscribeView, so both paths see the same rows)
    bot_plan, _ = _ensure_bot_plan(code.bot_plan)
    duplicate = (
        BotSubscription.objects.filter(user=user, plan=bot_plan)
        .exclude(status__in=TERMINAL_STATUSES)
        .first()
    )
    if duplicate:
        raise Conflict(
            {
                "message": "You already have an active or pending subscription to this plan",
                "subscription_id": str(duplicate.id),
                "status": duplicate.status,
            }
        )


def _ensure_bot_plan(plan):
    """Resolve-or-create the BotSubscriptionPlan shim (legacy SubscribeView logic)."""
    bot_plan, created = BotSubscriptionPlan.objects.get_or_create(
        name=plan.name,
        bot_type="custom",
        defaults={
            "price": plan.price_monthly,
            "duration_days": 30,
            "features": {
                "max_bots": plan.max_bots_allowed,
                "max_webhooks": plan.max_webhooks_allowed,
            },
            "is_active": True,
            # G5 tier bridge: keep the Model C tier link set on new shims
            # (legacy rows linked by migration 0013 backfill).
            "subscription_plan": plan,
        },
    )
    if not created and bot_plan.subscription_plan_id is None:
        # Defensive: a pre-G5 shim whose name did not exist at backfill time.
        bot_plan.subscription_plan = plan
        bot_plan.save(update_fields=["subscription_plan"])
    return bot_plan, created


def fulfill_payment_code(
    code: PaymentCode,
    *,
    payment_screenshot,
    payment_transaction_hash: str,
    payment_blockchain: str,
    telegram_handle: str = "",
):
    """
    Validate proof against an awaiting-payment code, create the downstream
    subscription (pending_approval — admin verifies manually at launch),
    freeze the quote audit fields, and mark the code `submitted`.

    Returns the created TelegramSubscription or BotSubscription.
    Raises Conflict (409) on stale code / duplicate / capacity, and
    DRF ValidationError (400) on missing proof/handle.
    """
    if code.status != "awaiting_payment":
        raise Conflict(
            {
                "message": f"Payment code is {code.get_status_display().lower()}",
                "code": code.code,
                "status": code.status,
            }
        )
    if not (payment_screenshot or payment_transaction_hash):
        raise serializers.ValidationError("Payment proof required")

    # Freeze the price audit BEFORE creating the subscription: view calls
    # get_or_refresh_quote() first, so locked_* comes from a live quote.
    quote = code.current_quote

    if code.order_kind == "telegram_signal":
        handle = str(telegram_handle or "").strip()
        if not handle:
            raise serializers.ValidationError("telegram_handle required")
        check_order_allowed(code)
        subscription = TelegramSubscription.objects.create(
            user=code.user,
            plan=code.telegram_plan,
            status="pending_approval",
            telegram_handle=handle,
            payment_screenshot=payment_screenshot,
            payment_transaction_hash=payment_transaction_hash,
            payment_blockchain=payment_blockchain,
            amount_paid=code.fiat_amount,  # net — discount is baked into fiat_amount
            discount_applied=code.discount_applied,
            billing_cycle=code.billing_cycle,
        )
    else:
        check_order_allowed(code)
        bot_plan, _ = _ensure_bot_plan(code.bot_plan)
        subscription = BotSubscription.objects.create(
            user=code.user,
            plan=bot_plan,
            status="pending_approval",
            payment_screenshot=payment_screenshot,
            payment_transaction_hash=payment_transaction_hash,
            payment_blockchain=payment_blockchain,
            # G5 / FR A7: net payable frozen on the code (= plan price when
            # no discount) — commission accrues on amount_due, never on a
            # hypothetical full price the user never paid.
            discount_applied=code.discount_applied,
            amount_due=code.fiat_amount,
        )

    code.status = "submitted"
    code.subscription_id = str(subscription.id)
    if quote is not None:
        code.locked_rate = quote.rate
        code.locked_crypto_amount = quote.crypto_amount
        code.locked_coin = quote.coin.coin
    code.save()

    logger.info(
        "payment code %s submitted → %s (%s)",
        code.code,
        code.subscription_id,
        code.order_kind,
    )
    return subscription


def plan_fiat_amount(order_kind: str, plan, billing_cycle: str) -> Decimal:
    """Frozen USD amount for the code (telegram honours cycle, bot = monthly)."""
    if order_kind == "telegram_signal":
        cycle_prices = {
            "monthly": plan.price_monthly,
            "quarterly": plan.price_quarterly,
            "yearly": plan.price_yearly,
        }
        if billing_cycle not in cycle_prices:
            raise serializers.ValidationError(
                "billing_cycle must be one of: monthly, quarterly, yearly"
            )
        return Decimal(cycle_prices[billing_cycle])
    return Decimal(plan.price_monthly)


# Re-export for view-level convenience (keep model import surface small).
__all__ = [
    "check_order_allowed",
    "fulfill_payment_code",
    "plan_fiat_amount",
]
