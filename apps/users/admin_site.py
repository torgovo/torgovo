from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

UserModel = get_user_model()


class TorgovoAdminSite(AdminSite):
    site_header = "Torgovo Trading Platform"
    site_title = "Torgovo Admin"
    index_title = "Platform Control Panel"
    site_url = "/api/"

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        today = timezone.now()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            from apps.bots.models import GridBot, MartingaleBot, QuantumAIBot, SignalBot
            from apps.payments.models import BotSubscription, WithdrawalRequest

            total_users = UserModel.objects.count()
            new_users_today = UserModel.objects.filter(date_joined__date=today.date()).count()
            active_subs = BotSubscription.objects.filter(status="active").count()

            bots_running = (
                GridBot.objects.filter(is_running=True).count()
                + MartingaleBot.objects.filter(is_running=True).count()
                + QuantumAIBot.objects.filter(is_running=True).count()
                + SignalBot.objects.filter(is_active=True).count()
            )
            total_bots = (
                GridBot.objects.count()
                + MartingaleBot.objects.count()
                + QuantumAIBot.objects.count()
                + SignalBot.objects.count()
            )

            monthly_revenue = (
                BotSubscription.objects.filter(
                    created_at__gte=month_start, status="active"
                ).aggregate(total=Sum("plan__price"))["total"]
                or 0
            )

            pending_withdrawals = WithdrawalRequest.objects.filter(status="pending").count()
            pending_amount = (
                WithdrawalRequest.objects.filter(status="pending").aggregate(total=Sum("amount"))[
                    "total"
                ]
                or 0
            )

            extra_context["kpi_data"] = {
                "total_users": total_users,
                "new_users_today": new_users_today,
                "active_subscriptions": active_subs,
                "bots_running": bots_running,
                "total_bots": total_bots,
                "monthly_revenue": float(monthly_revenue),
                "pending_withdrawals": pending_withdrawals,
                "pending_withdrawal_amount": float(pending_amount),
            }
        except Exception:
            extra_context["kpi_data"] = {}

        return super().index(request, extra_context=extra_context)


admin_site = TorgovoAdminSite(name="admin")
