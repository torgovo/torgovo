"""
Business logic for subscription approval workflow.
Handles state transitions and side effects.
"""

import logging

from django.db import transaction
from django.db.models import Q

from apps.bots.models import QuantumAIFund, QuantumAIInvestment
from apps.payments.models import BotSubscription
from core.models import AuditLog

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Service layer for subscription lifecycle management.
    """

    @staticmethod
    @transaction.atomic
    def approve_subscription(subscription_id: str, admin_user, notes: str = ""):
        """
        Approve a pending subscription and create necessary records.

        Args:
            subscription_id: UUID of BotSubscription
            admin_user: Admin user approving
            notes: Optional admin notes
        """
        try:
            subscription = BotSubscription.objects.select_for_update().get(id=subscription_id)

            if subscription.status not in ["pending_payment", "pending_approval"]:
                raise ValueError(f"Cannot approve subscription with status: {subscription.status}")

            # Approve the subscription
            subscription.approve(admin_user, notes)

            bot_type = subscription.plan.bot_type

            # Create bot/fund based on type
            if bot_type == "quantum_ai":
                SubscriptionService._create_quantum_ai_investment(subscription)

            # Log the approval
            AuditLog.objects.create(
                user=admin_user,
                action="bot_subscription_approved",
                resource_type="BotSubscription",
                resource_id=str(subscription.id),
                description=f"Approved {bot_type} subscription for {subscription.user.email}",
            )

            logger.info(f"Approved {bot_type} subscription for {subscription.user.email}")
            return subscription

        except Exception as e:
            logger.error(f"Error approving subscription {subscription_id}: {e}")
            raise

    @staticmethod
    def _create_quantum_ai_investment(subscription: BotSubscription):
        """Create Quantum AI investment record"""
        # Get the master fund (should exist, created by admin)
        fund = QuantumAIFund.objects.filter(is_active=True).first()

        if not fund:
            raise ValueError("No active Quantum AI fund found. Admin must create one first.")

        # Calculate USDT amount from subscription plan price
        usdt_amount = subscription.plan.price

        # Create investment
        investment = QuantumAIInvestment.objects.create(
            user=subscription.user,
            fund=fund,
            subscription=subscription,
            amount=usdt_amount,
            status="pending",
        )

        # Calculate share percentage
        investment.share_percentage = investment.calculate_share_percentage()
        investment.save()

        logger.info(
            f"Created Quantum AI investment for {subscription.user.email}: {usdt_amount} USDT"
        )

    @staticmethod
    @transaction.atomic
    def reject_subscription(subscription_id: str, admin_user, reason: str):
        """Reject a pending subscription"""
        subscription = BotSubscription.objects.select_for_update().get(id=subscription_id)

        if subscription.status not in ["pending_payment", "pending_approval"]:
            raise ValueError(f"Cannot reject subscription with status: {subscription.status}")

        subscription.reject(admin_user, reason)

        # Log the rejection
        AuditLog.objects.create(
            user=admin_user,
            action="bot_subscription_rejected",
            resource_type="BotSubscription",
            resource_id=str(subscription.id),
            new_values={"rejection_reason": reason},
            description=f"Rejected {subscription.plan.bot_type} subscription: {reason}",
        )

        logger.info(f"Rejected subscription {subscription_id}: {reason}")
        return subscription

    @staticmethod
    def get_pending_subscriptions():
        """Get all subscriptions pending approval"""
        return (
            BotSubscription.objects.filter(status="pending_approval")
            .select_related("user", "plan")
            .order_by("-created_at")
        )

    @staticmethod
    def get_subscription_dashboard_stats():
        """Get subscription statistics for admin dashboard"""
        from django.db.models import Count, Sum

        stats = BotSubscription.objects.aggregate(
            total=Count("id"),
            pending_approval=Count("id", filter=Q(status="pending_approval")),
            active=Count("id", filter=Q(status="active")),
            expired=Count("id", filter=Q(status="expired")),
            total_revenue=Sum("plan__price", filter=Q(status="active")),
        )

        return stats
