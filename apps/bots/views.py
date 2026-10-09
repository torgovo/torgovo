"""
Views for bot management endpoints.

All bot CRUD operations, start/stop controls, and admin indicator views.
Separated from apps/payments/views.py for clean concern separation.
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.bots.models import (
    BotOrder,
    GridBot,
    Indicator,
    InvestorPortfolio,
    MartingaleBot,
    PairConfig,
    QuantumAIFund,
    SignalBot,
)
from apps.bots.serializers import (
    GridBotCreateSerializer,
    GridBotSerializer,
    IndicatorSerializer,
    InvestorPortfolioSerializer,
    MartingaleBotCreateSerializer,
    MartingaleBotSerializer,
    OrderSerializer,
    PairConfigSerializer,
    QuantumAIFundSerializer,
    SignalBotCreateSerializer,
    SignalBotSerializer,
)
from apps.payments.models import BotSubscription
from core.pagination import StandardResultsSetPagination

logger = logging.getLogger("bots")


def get_or_create_engine(user, pair_config, exchange_name):
    """Get existing BotEngine or create a new one for this user/pair/exchange.

    Accepts either a PairConfig model instance or a dict with a 'pair_symbol' key.
    Delegates to the shared implementation in indicators_views.
    """
    from .indicators_views import _get_or_create_engine

    # Handle dict input (e.g., from tests)
    if isinstance(pair_config, dict):

        # Create a simple namespace object so _get_or_create_engine works
        class _DictWrapper:
            pass

        wrapper = _DictWrapper()
        wrapper.pair_symbol = pair_config.get("pair_symbol", "")
        wrapper.quantity = pair_config.get("quantity", 0)
        wrapper.favor_levels = pair_config.get("favor_levels", 3)
        wrapper.against_levels = pair_config.get("against_levels", 3)
        wrapper.favor_level_qty = pair_config.get("favor_level_qty", 0)
        wrapper.against_level_qty = pair_config.get("against_level_qty", 0)
        wrapper.favor_level_difference = pair_config.get("favor_level_difference", 0.5)
        wrapper.against_level_difference = pair_config.get("against_level_difference", 0.5)
        wrapper.Order_Type = pair_config.get("Order_Type", "market")
        wrapper.Amount_Type = pair_config.get("Amount_Type", "dollar")
        wrapper.SLTP_Type = pair_config.get("SLTP_Type", "dollar")
        wrapper.Stop_Loss = pair_config.get("Stop_Loss")
        wrapper.Take_Profit = pair_config.get("Take_Profit")
        return _get_or_create_engine(user, wrapper, exchange_name)

    return _get_or_create_engine(user, pair_config, exchange_name)


# ==================== SIGNAL BOT (TradingView Webhook) ====================


class SignalBotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Signal Bots (TradingView webhook bots).
    Users create a signal bot, get a webhook URL, and connect it to TradingView.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return SignalBot.objects.all()
        return SignalBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return SignalBotCreateSerializer
        return SignalBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type="custom", status="active"
        ).first()

        if not subscription:
            raise PermissionError("No active Signal Bot subscription")

        bot = serializer.save(user=self.request.user, subscription=subscription)
        bot.generate_webhook_credentials()

    @action(detail=True, methods=["post"])
    def toggle_active(self, request, pk=None):
        """Toggle bot active/inactive status"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        bot.is_active = not bot.is_active
        bot.save()

        return Response(
            {
                "success": True,
                "is_active": bot.is_active,
                "message": f'Bot {bot.bot_name} is now {"active" if bot.is_active else "inactive"}',
            }
        )


# ==================== GRID BOT ====================


class GridBotViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Grid Trading bots"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return GridBot.objects.all()
        return GridBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return GridBotCreateSerializer
        return GridBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type="grid", status="active"
        ).first()

        if not subscription:
            raise PermissionError("No active Grid Bot subscription")

        existing_bot = GridBot.objects.filter(subscription=subscription, is_deleted=False).first()

        if existing_bot:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "You already have a Grid Bot for this subscription. "
                "You can update the existing bot's settings instead."
            )

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start the grid bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        if not bot.subscription or bot.subscription.status != "active":
            return Response({"error": "No active subscription"}, status=status.HTTP_400_BAD_REQUEST)

        from services.bot_executor import BotExecutorService

        try:
            BotExecutorService.start_grid_bot(request.user, str(bot.id))
            return Response({"success": True, "message": "Grid bot started"})
        except Exception as e:
            logger.error(f"Grid bot start error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return Response(
                {"error": "Failed to start bot"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """Stop the grid bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        from services.bot_executor import BotExecutorService

        try:
            BotExecutorService.stop_grid_bot(request.user, str(bot.id))
            return Response({"success": True, "message": "Grid bot stopped"})
        except Exception as e:
            logger.error(f"Grid bot stop error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return Response(
                {"error": "Failed to stop bot"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== MARTINGALE BOT ====================


class MartingaleBotViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Martingale bots"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return MartingaleBot.objects.all()
        return MartingaleBot.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return MartingaleBotCreateSerializer
        return MartingaleBotSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type="martingale", status="active"
        ).first()

        if not subscription:
            raise PermissionError("No active Martingale Bot subscription")

        existing_bot = MartingaleBot.objects.filter(
            subscription=subscription, is_deleted=False
        ).first()

        if existing_bot:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "You already have a Martingale Bot for this subscription. "
                "You can update the existing bot's settings instead."
            )

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start the martingale bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        if not bot.subscription or bot.subscription.status != "active":
            return Response({"error": "No active subscription"}, status=status.HTTP_400_BAD_REQUEST)

        from services.bot_executor import BotExecutorService

        try:
            BotExecutorService.start_martingale_bot(request.user, str(bot.id))
            return Response({"success": True, "message": "Martingale bot started"})
        except Exception as e:
            logger.error(f"Martingale bot start error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return Response(
                {"error": "Failed to start bot"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """Stop the martingale bot"""
        bot = self.get_object()

        if bot.user != request.user and not request.user.is_staff:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        from services.bot_executor import BotExecutorService

        try:
            BotExecutorService.stop_martingale_bot(request.user, str(bot.id))
            return Response({"success": True, "message": "Martingale bot stopped"})
        except Exception as e:
            logger.error(f"Martingale bot stop error: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return Response(
                {"error": "Failed to stop bot"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== QUANTUM AI ====================


class QuantumAIFundViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Quantum AI Fund (Admin only)"""

    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination
    queryset = QuantumAIFund.objects.all()
    serializer_class = QuantumAIFundSerializer


class InvestorPortfolioViewSet(viewsets.ModelViewSet):
    """ViewSet for user's Quantum AI investments"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return InvestorPortfolio.objects.all()
        return InvestorPortfolio.objects.filter(user=self.request.user)

    serializer_class = InvestorPortfolioSerializer

    def perform_create(self, serializer):
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type="quantum_ai", status="active"
        ).first()

        if not subscription:
            raise PermissionError("No active Quantum AI subscription")

        serializer.save(user=self.request.user, subscription=subscription)

    @action(detail=False, methods=["get"])
    def balance(self, request):
        """Get user's current Quantum AI balance"""
        investments = self.get_queryset().filter(status="active")
        total_invested = sum(inv.amount for inv in investments)
        total_profit = sum(inv.accrued_profit for inv in investments)
        return Response(
            {
                "total_invested": str(total_invested),
                "total_profit": str(total_profit),
                "current_balance": str(total_invested + total_profit),
            }
        )


# ==================== PAIR CONFIG ====================


class PairConfigViewSet(viewsets.ModelViewSet):
    """ViewSet for PairConfig"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return PairConfig.objects.all()
        return PairConfig.objects.filter(user=self.request.user)

    serializer_class = PairConfigSerializer

    def perform_create(self, serializer):
        bot_type = serializer.validated_data.get("bot_type", "grid")
        subscription = BotSubscription.objects.filter(
            user=self.request.user, plan__bot_type=bot_type, status="active"
        ).first()

        if not subscription:
            raise PermissionError(f"No active subscription for {bot_type} bot")

        serializer.save(user=self.request.user, subscription=subscription)


# ==================== INDICATOR ====================


class IndicatorViewSet(viewsets.ModelViewSet):
    """ViewSet for technical indicators"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return Indicator.objects.all()
        return Indicator.objects.filter(user=self.request.user)

    serializer_class = IndicatorSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ==================== ORDER ====================


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for orders (read-only history)"""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if self.request.user.is_staff:
            return BotOrder.objects.all()

        return BotOrder.objects.filter(user=self.request.user)

    serializer_class = OrderSerializer

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent orders"""
        recent_orders = self.get_queryset().select_related(
            "signal_bot", "grid_bot", "martingale_bot", "quantum_ai_investment"
        )[:50]
        serializer = self.get_serializer(recent_orders, many=True)
        return Response(serializer.data)
