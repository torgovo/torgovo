"""
Views for user management.
User-facing account endpoints (deactivation / GDPR data export) plus
admin-only user management views.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import (
    BotOrder,
    GridBot,
    InvestorPortfolio,
    MartingaleBot,
    PairConfig,
    QuantumAIBot,
    QuantumDeposit,
    QuantumWeeklyProfit,
    SignalBot,
)
from apps.exchanges.models import ExchangeCredentials
from apps.investments.models import Order as InvestmentOrder
from apps.payments.models import BlockchainAddress, BotSubscription
from apps.payments.models import InvestorDeposit as Deposit
from apps.payments.models import PaymentTransaction, WithdrawalRequest
from apps.referrals.models import Referral
from apps.subscriptions.models import TelegramSubscription
from apps.users.models import UserBalance
from core.models import AuditLog, UserActivityLog
from core.pagination import StandardResultsSetPagination
from core.permissions import IsAdminUser
from core.utils import get_client_ip

from .admin_serializers import UserAdminDetailSerializer, UserAdminSerializer
from .serializers import DeactivateAccountSerializer

logger = logging.getLogger("apps")

User = get_user_model()


class UserListView(generics.ListAPIView):
    """List all users (admin only)."""

    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["is_active", "is_staff", "date_joined"]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Annotate with additional fields
        queryset = queryset.annotate(
            total_deposits=Count("quantum_deposits", distinct=True),
            active_bots_count=Count(
                Q(signal_bots__is_active=True)
                | Q(grid_bots__is_running=True)
                | Q(martingale_bots__is_running=True)
                | Q(quantum_ai_investments__status="active"),
                distinct=True,
            ),
        )

        return queryset


class UserDetailView(generics.RetrieveUpdateAPIView):
    """Get or update user details (admin only)."""

    queryset = User.objects.all()
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminDetailSerializer


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    """Get comprehensive admin dashboard statistics."""
    try:
        # Time ranges
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)

        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(last_login__gte=last_30_days).count()
        new_users_today = User.objects.filter(date_joined__date=today).count()
        new_users_month = User.objects.filter(date_joined__gte=last_30_days).count()

        # Subscription statistics
        subscription_stats = {}

        SUBSCRIPTION_PLANS = [
            ("free", "Free"),
            ("basic", "Basic"),
            ("premium", "Premium"),
            ("enterprise", "Enterprise"),
        ]
        for plan_type, display_name in SUBSCRIPTION_PLANS:
            count = User.objects.filter(subscription_plan=plan_type).count()
            subscription_stats[plan_type] = {
                "count": count,
                "display_name": display_name,
                "percentage": (count / total_users * 100) if total_users > 0 else 0,
            }

        # Bot statistics
        total_webhooks = SignalBot.objects.count()
        total_grid_bots = GridBot.objects.count()
        total_martingale_bots = MartingaleBot.objects.count()
        total_quantum_bots = QuantumAIBot.objects.count()

        running_bots = (
            SignalBot.objects.filter(is_active=True).count()
            + GridBot.objects.filter(is_running=True).count()
            + MartingaleBot.objects.filter(is_running=True).count()
            + QuantumAIBot.objects.filter(is_running=True).count()
        )

        # Trading statistics
        total_trades = InvestmentOrder.objects.count()
        trades_today = InvestmentOrder.objects.filter(created_at__date=today).count()
        trades_month = InvestmentOrder.objects.filter(created_at__gte=last_30_days).count()

        # Financial statistics
        total_deposits = Deposit.objects.filter(status="approved").aggregate(
            total=Sum("amount"), count=Count("id")
        )

        pending_deposits = Deposit.objects.filter(status="pending").count()

        # Exchange distribution
        exchange_stats = {}
        for webhook in SignalBot.objects.values("exchange_name").annotate(count=Count("id")):
            exchange_stats[webhook["exchange_name"]] = webhook["count"]

        return Response(
            {
                "user_statistics": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "new_users_today": new_users_today,
                    "new_users_month": new_users_month,
                    "subscription_distribution": subscription_stats,
                },
                "bot_statistics": {
                    "total_bots": total_webhooks
                    + total_grid_bots
                    + total_martingale_bots
                    + total_quantum_bots,
                    "running_bots": running_bots,
                    "webhook_alerts": total_webhooks,
                    "grid_bots": total_grid_bots,
                    "martingale_bots": total_martingale_bots,
                    "quantum_ai_bots": total_quantum_bots,
                    "exchange_distribution": exchange_stats,
                },
                "trading_statistics": {
                    "total_trades": total_trades,
                    "trades_today": trades_today,
                    "trades_month": trades_month,
                },
                "financial_statistics": {
                    "total_deposits_usdt": float(total_deposits["total"] or 0),
                    "total_deposit_count": total_deposits["count"],
                    "pending_deposits": pending_deposits,
                },
            }
        )

    except Exception as e:
        logger.error(f"admin_dashboard error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load dashboard"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_create_blockchain_address(request):
    """Create new blockchain address for deposits (admin only)."""
    try:
        coin_type = request.data.get("coin_type")
        blockchain = request.data.get("blockchain")
        address = request.data.get("address")

        if not all([coin_type, blockchain, address]):
            return Response(
                {"error": "Missing required fields: coin_type, blockchain, address"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        blockchain_addr = BlockchainAddress.objects.create(
            coin_type=coin_type, blockchain=blockchain, address=address, is_active=True
        )

        return Response(
            {
                "message": "Blockchain address created successfully",
                "address": {
                    "id": str(blockchain_addr.id),
                    "coin_type": blockchain_addr.coin_type,
                    "blockchain": blockchain_addr.blockchain,
                    "address": blockchain_addr.address,
                    "is_active": blockchain_addr.is_active,
                    "created_at": blockchain_addr.created_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"admin_create_blockchain_address error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to create address"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_bots_overview(request):
    """Get overview of all running bots (admin only)."""
    try:
        # Bot counts by type and status
        webhook_stats = {
            "total": SignalBot.objects.count(),
            "active": SignalBot.objects.filter(is_active=True).count(),
            "running": 0,  # Webhook alerts don't have running state
            "exchanges": {},
        }

        grid_stats = {
            "total": GridBot.objects.count(),
            "active": GridBot.objects.filter(is_running=True).count(),
            "running": GridBot.objects.filter(is_running=True).count(),
            "exchanges": {},
        }

        martingale_stats = {
            "total": MartingaleBot.objects.count(),
            "active": MartingaleBot.objects.filter(is_running=True).count(),
            "running": MartingaleBot.objects.filter(is_running=True).count(),
            "exchanges": {},
        }

        quantum_stats = {
            "total": QuantumAIBot.objects.count(),
            "active": QuantumAIBot.objects.filter(is_running=True).count(),
            "running": 0,  # Quantum AI bots have different state
            "total_deposited": 0,
            "total_profit_loss": float(
                QuantumAIBot.objects.aggregate(total=Sum("total_profit_loss"))["total"] or 0
            ),
        }

        # Exchange distribution — batched queries instead of N+1 loop
        from apps.exchanges.models import Exchange, ExchangeCredentials

        exchanges = list(Exchange.objects.filter(is_active=True).values_list("name", flat=True))
        if not exchanges:
            exchanges = [code for code, _ in ExchangeCredentials.EXCHANGE_CHOICES]

        webhook_by_exchange = {
            item["exchange_name"]: item["count"]
            for item in SignalBot.objects.values("exchange_name")
            .annotate(count=Count("id"))
            .filter(exchange_name__in=exchanges)
        }
        grid_by_exchange = {
            item["exchange_name"]: item["count"]
            for item in GridBot.objects.values("exchange_name")
            .annotate(count=Count("id"))
            .filter(exchange_name__in=exchanges)
        }
        martingale_by_exchange = {
            item["exchange_name"]: item["count"]
            for item in MartingaleBot.objects.values("exchange_name")
            .annotate(count=Count("id"))
            .filter(exchange_name__in=exchanges)
        }

        for exchange in exchanges:
            webhook_stats["exchanges"][exchange] = webhook_by_exchange.get(exchange, 0)
            grid_stats["exchanges"][exchange] = grid_by_exchange.get(exchange, 0)
            martingale_stats["exchanges"][exchange] = martingale_by_exchange.get(exchange, 0)

        return Response(
            {
                "total_bots": (
                    webhook_stats["total"]
                    + grid_stats["total"]
                    + martingale_stats["total"]
                    + quantum_stats["total"]
                ),
                "running_bots": (
                    webhook_stats["running"] + grid_stats["running"] + martingale_stats["running"]
                ),
                "total_users": User.objects.count(),
                "daily_trades": InvestmentOrder.objects.filter(
                    created_at__date=timezone.now().date()
                ).count(),
                "platform_volume": float(
                    InvestmentOrder.objects.aggregate(total=Sum("quantity"))["total"] or 0
                ),
                "by_type": {
                    "webhook_alerts": webhook_stats,
                    "grid_bots": grid_stats,
                    "martingale_bots": martingale_stats,
                    "quantum_ai": quantum_stats,
                },
                "by_exchange": {
                    exchange: (
                        webhook_stats["exchanges"][exchange]
                        + grid_stats["exchanges"][exchange]
                        + martingale_stats["exchanges"][exchange]
                    )
                    for exchange in exchanges
                },
            }
        )

    except Exception as e:
        logger.error(f"admin_bots_overview error: {e}", exc_info=True)
        return Response(
            {"error": "Failed to load bot overview"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_trade_logs(request):
    """View all trade logs with filters (admin only)."""
    queryset = BotOrder.objects.all().select_related(
        "user", "signal_bot", "grid_bot", "martingale_bot"
    )

    # Apply filters
    user_id = request.query_params.get("user_id")
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    exchange = request.query_params.get("exchange")
    if exchange:
        queryset = queryset.filter(exchange=exchange)

    bot_id = request.query_params.get("bot_id")
    if bot_id:
        queryset = queryset.filter(
            Q(signal_bot_id=bot_id) | Q(grid_bot_id=bot_id) | Q(martingale_bot_id=bot_id)
        )

    start_date = request.query_params.get("start_date")
    if start_date:
        queryset = queryset.filter(timestamp__gte=start_date)

    end_date = request.query_params.get("end_date")
    if end_date:
        queryset = queryset.filter(timestamp__lte=end_date)

    # Paginate results
    paginator = StandardResultsSetPagination()
    result_page = paginator.paginate_queryset(queryset, request)

    from apps.bots.serializers import OrderSerializer

    serializer = OrderSerializer(result_page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_restrict_user(request, pk):
    """Restrict/disable user account (admin only)."""
    try:
        user = User.objects.get(pk=pk)

        action = request.data.get("action", "disable")

        if action == "disable":
            user.is_active = False
        elif action == "enable":
            user.is_active = True
        elif action == "restrict":
            user.is_active = False
        else:
            return Response(
                {"error": 'Invalid action. Use "enable", "disable", or "restrict"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.save()

        return Response(
            {
                "message": f"User {user.email} has been {action}d",
                "user_id": str(user.pk),
                "is_active": user.is_active,
            }
        )

    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@shared_task
def send_bulk_email_task(subject, message, recipient_list):
    """Send bulk emails via Celery worker."""
    sent_count = 0
    for recipient in recipient_list:
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient])
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
    return sent_count


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_send_email(request):
    """Send emails (system-wide or targeted) (admin only)."""
    email_type = request.data.get("type", "system")
    subject = request.data.get("subject")
    message = request.data.get("message")
    recipients = request.data.get("recipients", [])  # List of user IDs or 'all'

    if not subject or not message:
        return Response(
            {"error": "Subject and message are required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        if email_type == "system":
            if recipients == "all":
                users = list(User.objects.filter(is_active=True).values_list("email", flat=True))
            else:
                users = list(
                    User.objects.filter(id__in=recipients, is_active=True).values_list(
                        "email", flat=True
                    )
                )

            send_bulk_email_task.delay(subject, message, users)

            return Response(
                {
                    "message": f"Email task dispatched to Celery for {len(users)} users",
                    "dispatched": len(users),
                }
            )

        else:
            return Response({"error": "Invalid email type"}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response(
            {"error": f"Failed to send emails: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def admin_process_withdrawals(request):
    """Process manual withdrawals every 2 weeks (admin only)."""
    try:
        pending_withdrawals = WithdrawalRequest.objects.filter(status="pending")

        if not pending_withdrawals.exists():
            return Response({"message": "No pending withdrawals to process", "processed": 0})

        successful = 0
        failed = 0

        for withdrawal in pending_withdrawals:
            try:
                withdrawal.status = "completed"
                withdrawal.save()
                successful += 1
            except Exception as e:
                withdrawal.status = "failed"
                withdrawal.error_message = str(e)
                withdrawal.save()
                failed += 1

        return Response(
            {
                "message": f"Processed {successful} withdrawals ({failed} failed)",
                "successful": successful,
                "failed": failed,
            }
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to process withdrawals: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ---------------------------------------------------------------------------
# User-facing account endpoints (deactivation / GDPR data export)
# ---------------------------------------------------------------------------


def _mask_credential(value):
    """Mask a secret, keeping only the first/last 4 chars for identification."""
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _log_activity(user, request, action, description, status_code):
    """Write an audit trail entry for a user-facing account action."""
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    UserActivityLog.objects.create(
        user=user,
        action=action,
        description=description,
        ip_address=ip,
        user_agent=user_agent,
        endpoint=request.path,
        method=request.method,
        status_code=status_code,
    )


class DeactivateAccountView(APIView):
    """Let a user permanently deactivate their own account (GDPR Art. 17 right to erasure).

    Deactivation keeps the account row (so duplicate signups stay blocked and
    financial records keep referential integrity) but disables login and
    revokes every outstanding refresh token. Only the account owner can call it,
    and they must re-authenticate with their current password.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if not user.is_active:
            return Response(
                {"detail": "Account is already deactivated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DeactivateAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # Disable the account — this blocks login (authenticate checks is_active).
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])

        # Revoke every outstanding refresh token so no session can continue.
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        tokens = list(OutstandingToken.objects.filter(user=user))
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        revoked = len(tokens)

        # Audit trail for both the security log and the user activity feed.
        ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        AuditLog.objects.create(
            user=user,
            action="update",
            resource_type="user_account",
            resource_id=str(user.pk),
            old_values={"is_active": True},
            new_values={"is_active": False},
            description="User deactivated their own account (GDPR erasure request)",
            ip_address=ip,
            user_agent=user_agent,
        )
        _log_activity(
            user,
            request,
            "account_deactivated",
            "User deactivated their own account",
            status.HTTP_200_OK,
        )

        return Response(
            {
                "detail": "Account deactivated. You will not be able to log in again. "
                "Contact support to reactivate.",
                "sessions_revoked": revoked,
            },
            status=status.HTTP_200_OK,
        )


class UserDataExportView(APIView):
    """Export all of a user's personal data as JSON (GDPR Art. 15 access right).

    Every model owned by the user is included. Exchange API credentials are
    masked (they are encrypted at rest and are never needed to be shown in
    plaintext); everything else is the user's own data returned as-is.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Soft-delete-aware querysets: only live rows are exported.
        def live(qs):
            return qs.filter(is_deleted=False)

        credentials = []
        for cred in ExchangeCredentials.objects.filter(user=user, is_deleted=False):
            decrypted = cred.get_decrypted_credentials()
            credentials.append(
                {
                    "id": str(cred.pk),
                    "exchange_name": cred.exchange_name,
                    "api_key": _mask_credential(decrypted.get("api_key")),
                    "secret_key": _mask_credential(decrypted.get("secret_key")),
                    "passphrase": _mask_credential(decrypted.get("passphrase")),
                    "is_testnet": cred.is_testnet,
                    "is_active": cred.is_active,
                    "permissions": cred.permissions,
                    "verification_status": cred.verification_status,
                    "last_verified": cred.last_verified,
                    "created_at": cred.created_at,
                }
            )

        data = {
            "profile": {
                "id": str(user.pk),
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "subscription_plan": getattr(user, "subscription_plan", None),
                "is_subscription_active": user.is_subscription_active,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
            },
            "balances": list(UserBalance.objects.filter(user=user).values()),
            "exchange_credentials": credentials,
            "bots": {
                "signal_bots": list(live(SignalBot.objects.filter(user=user)).values()),
                "grid_bots": list(live(GridBot.objects.filter(user=user)).values()),
                "martingale_bots": list(live(MartingaleBot.objects.filter(user=user)).values()),
                "pair_configs": list(PairConfig.objects.filter(user=user).values()),
            },
            "quantum_ai": {
                "investments": list(live(InvestorPortfolio.objects.filter(user=user)).values()),
                "deposits": list(live(QuantumDeposit.objects.filter(user=user)).values()),
                "weekly_profits": list(
                    live(QuantumWeeklyProfit.objects.filter(user=user)).values()
                ),
            },
            "orders": {
                "bot_orders": list(BotOrder.objects.filter(user=user).values()),
                "investment_orders": list(InvestmentOrder.objects.filter(user=user).values()),
            },
            "payments": {
                "deposits": list(live(Deposit.objects.filter(user=user)).values()),
                "withdrawal_requests": list(
                    live(WithdrawalRequest.objects.filter(user=user)).values()
                ),
                "payment_transactions": list(PaymentTransaction.objects.filter(user=user).values()),
                "bot_subscriptions": list(live(BotSubscription.objects.filter(user=user)).values()),
            },
            "subscriptions": list(live(TelegramSubscription.objects.filter(user=user)).values()),
            "referrals": {
                "referrals_made": list(Referral.objects.filter(referrer=user).values()),
                "referral_received": list(Referral.objects.filter(referred_user=user).values()),
            },
            "activity_logs": list(live(UserActivityLog.objects.filter(user=user)).values()),
        }

        return Response(data, status=status.HTTP_200_OK)
