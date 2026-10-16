"""
G1 / FR A2 — admin-driven Model C plans.

Covers:
- seed_model_c_plans command: creates the 5 locked grill-me plan rows,
  idempotent on re-run, safe --dry-run, re-asserts Model C prices.
- Plans API: exposes every admin-driven field, ordered by sort_order.
- Cache invalidation: an admin edit propagates to the API immediately.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from rest_framework import status
from rest_framework.reverse import reverse

from apps.payments.models import SubscriptionPlan

# slug -> (monthly, yearly, sort_order) — locked grill-me values
MODEL_C_PRICES = {
    "free": ("0.00", "0.00", 10),
    "basic": ("15.00", "144.00", 20),
    "standard": ("25.00", "240.00", 30),
    "premium": ("49.00", "470.40", 40),
    "creator": ("20.00", "192.00", 50),
}


@pytest.mark.django_db
class TestSeedModelCPlans:
    def test_creates_all_five_locked_plans(self):
        call_command("seed_model_c_plans")
        assert SubscriptionPlan.objects.count() == 5
        for slug, (monthly, yearly, sort) in MODEL_C_PRICES.items():
            plan = SubscriptionPlan.objects.get(slug=slug)
            assert plan.price_monthly == Decimal(monthly)
            assert plan.price_yearly == Decimal(yearly)
            assert plan.sort_order == sort
            assert plan.is_active is True

    def test_free_tier_limits_match_fr_a2(self):
        call_command("seed_model_c_plans")
        free = SubscriptionPlan.objects.get(slug="free")
        assert free.bot_types == ["signal"]
        assert free.market == "spot"
        assert free.max_signals_per_month == 10
        assert free.max_exchanges == 1
        assert free.max_bots_allowed == 1

    def test_idempotent_second_run_creates_nothing(self):
        call_command("seed_model_c_plans")
        call_command("seed_model_c_plans")
        assert SubscriptionPlan.objects.count() == 5

    def test_dry_run_writes_nothing(self):
        call_command("seed_model_c_plans", "--dry-run")
        assert SubscriptionPlan.objects.count() == 0

    def test_reasserts_locked_prices_after_manual_drift(self):
        call_command("seed_model_c_plans")
        plan = SubscriptionPlan.objects.get(slug="premium")
        plan.price_monthly = Decimal("10.00")  # someone edits away from Model C
        plan.save()
        call_command("seed_model_c_plans")
        plan.refresh_from_db()
        assert plan.price_monthly == Decimal("49.00")

    def test_does_not_touch_noncanonical_slugs(self):
        SubscriptionPlan.objects.create(
            name="Custom",
            slug="custom",
            price_monthly=Decimal("7.00"),
            price_yearly=Decimal("70.00"),
            max_bots_allowed=3,
        )
        call_command("seed_model_c_plans")
        custom = SubscriptionPlan.objects.get(slug="custom")
        assert custom.price_monthly == Decimal("7.00")
        assert SubscriptionPlan.objects.count() == 6


@pytest.mark.django_db
class TestPlansApiAdminDriven:
    def test_bot_plans_expose_all_model_c_fields(self, api_client):
        call_command("seed_model_c_plans")
        response = api_client.get(reverse("subscriptions:plan-list"))
        assert response.status_code == status.HTTP_200_OK
        free = next(p for p in response.data["plans"] if p["slug"] == "free")
        for field in (
            "description",
            "price_monthly",
            "price_yearly",
            "annual_discount_pct",
            "sort_order",
            "max_bots_allowed",
            "max_webhooks_allowed",
            "bot_types",
            "market",
            "max_signals_per_month",
            "max_exchanges",
            "features",
            "trial_days",
        ):
            assert field in free, f"missing {field}"

    def test_bot_plans_ordered_by_sort_order(self, api_client):
        call_command("seed_model_c_plans")
        response = api_client.get(reverse("subscriptions:plan-list"))
        slugs = [p["slug"] for p in response.data["plans"]]
        assert slugs == ["free", "basic", "standard", "premium", "creator"]

    def test_annual_discount_pct_derived_not_hardcoded(self, api_client):
        call_command("seed_model_c_plans")
        response = api_client.get(reverse("subscriptions:plan-list"))
        basic = next(p for p in response.data["plans"] if p["slug"] == "basic")
        assert basic["annual_discount_pct"] == 20  # 15*12=180, yearly=144
        free = next(p for p in response.data["plans"] if p["slug"] == "free")
        assert free["annual_discount_pct"] == 0

    def test_payments_viewset_exposes_model_c_fields(self, auth_client):
        call_command("seed_model_c_plans")
        response = auth_client.get(reverse("payments:subscriptionplan-list"))
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert {r["slug"] for r in results} >= set(MODEL_C_PRICES)
        assert all("sort_order" in r and "market" in r for r in results)

    def test_admin_edit_propagates_to_api_immediately(self, api_client):
        """Editing a plan (as the admin does) must bust the plans cache."""
        call_command("seed_model_c_plans")
        url = reverse("subscriptions:plan-list")
        first = api_client.get(url)
        premium = next(p for p in first.data["plans"] if p["slug"] == "premium")
        assert premium["price_monthly"] == "49.00"

        # simulate admin save — post_save signal must drop the cache
        plan = SubscriptionPlan.objects.get(slug="premium")
        plan.price_monthly = Decimal("59.00")
        plan.save()

        second = api_client.get(url)
        premium = next(p for p in second.data["plans"] if p["slug"] == "premium")
        assert premium["price_monthly"] == "59.00"

    def test_bot_plans_public_no_auth(self, api_client):
        call_command("seed_model_c_plans")
        response = api_client.get(reverse("subscriptions:plan-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["plans"]) == 5
