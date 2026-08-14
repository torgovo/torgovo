from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="bots.BotOrder")
def sync_bot_order_to_investments(sender, instance, created, **kwargs):
    """
    Sync bots.BotOrder to investments.Order for portfolio display.

    Both models are kept:
    - bots.BotOrder  → bot execution log (source of truth)
    - investments.Order → portfolio display

    This lookup uses get_or_create on investments.Order, keyed by
    (user, exchange__name__iexact, trading_pair__symbol__iexact,
     side, price, quantity, created_at__date) to avoid duplicating
    the same executed order across refreshes.
    """
    if not created:
        return

    from decimal import Decimal

    from apps.exchanges.models import Exchange, TradingPair
    from apps.investments.models import Order as InvestmentOrder

    exchange, _ = Exchange.objects.get_or_create(
        name=instance.Exchange or "",
        defaults={"display_name": instance.Exchange or "", "is_active": False},
    )
    trading_pair, _ = TradingPair.objects.get_or_create(
        symbol=instance.Pair or "",
        defaults={
            "base_asset": (instance.Pair or "/").split("/")[0],
            "quote_asset": (
                (instance.Pair or "/").split("/")[1] if "/" in (instance.Pair or "") else ""
            ),
        },
    )

    price_val = Decimal(str(instance.Price)) if instance.Price else Decimal("0")
    qty_val = Decimal(str(instance.Quantity)) if instance.Quantity else Decimal("0")

    InvestmentOrder.objects.get_or_create(
        user=instance.user,
        exchange=exchange,
        trading_pair=trading_pair,
        side=instance.Side or "",
        order_type=instance.Order_type or "market",
        price=price_val,
        quantity=qty_val,
        defaults={
            "status": "filled",
            "description": instance.Description or "",
            "executed_at": instance.created_at,
        },
    )
