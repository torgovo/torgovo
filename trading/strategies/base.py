"""
Base trading strategy class
"""

import logging
import threading
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict

from django.conf import settings
from django.utils import timezone

from core.exceptions import TradingBotException

logger = logging.getLogger("trading")


class BaseTradingStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Provides common functionality and interface for different trading algorithms.
    """

    def __init__(
        self,
        user,
        exchange_bot: Any = None,
        exchange_bots: Dict[str, Any] = None,
        config: Dict[str, Any] = None,
    ):
        """
        Initialize trading strategy.

        Args:
            user: Django user instance
            exchange_bot: Single exchange bot instance
            exchange_bots: Multiple exchange bot instances (for multi-exchange strategies)
            config: Strategy configuration
        """
        self.user = user
        self.exchange_bot = exchange_bot
        self.exchange_bots = exchange_bots or {}
        self.config = config or {}
        self.is_running = False
        self.is_paused = False
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # Performance tracking
        self.total_trades = 0
        self.successful_trades = 0
        self.total_profit_loss = Decimal("0")
        self.start_time = None
        self.last_activity = None

        # Error handling
        self.last_error = None
        self.error_count = 0
        self.max_errors = getattr(settings, "MAX_STRATEGY_ERRORS", 10)

    @abstractmethod
    def start(self):
        """Start the trading strategy."""
        pass

    @abstractmethod
    def stop(self):
        """Stop the trading strategy."""
        pass

    @abstractmethod
    def execute_trade(self, signal: Dict[str, Any]) -> bool:
        """Execute a trade based on signal."""
        pass

    def pause(self):
        """Pause the trading strategy."""
        with self.lock:
            self.is_paused = True
            self.log_activity("pause", "Strategy paused")

    def resume(self):
        """Resume the trading strategy."""
        with self.lock:
            self.is_paused = False
            self.log_activity("resume", "Strategy resumed")

    def update_config(self, new_config: Dict[str, Any]):
        """Update strategy configuration."""
        with self.lock:
            old_config = self.config.copy()
            self.config.update(new_config)
            self.log_activity(
                "config_update", f"Configuration updated: {old_config} -> {self.config}"
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current strategy status."""
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "total_trades": self.total_trades,
            "successful_trades": self.successful_trades,
            "success_rate": self.calculate_success_rate(),
            "total_profit_loss": float(self.total_profit_loss),
            "start_time": self.start_time,
            "last_activity": self.last_activity,
            "last_error": self.last_error,
            "error_count": self.error_count,
        }

    def calculate_success_rate(self) -> float:
        """Calculate trade success rate."""
        if self.total_trades == 0:
            return 0.0
        return (self.successful_trades / self.total_trades) * 100

    def log_trade(self, trade_data: Dict[str, Any]):
        """Log trade execution."""
        self.total_trades += 1
        self.last_activity = timezone.now()

        if trade_data.get("profit_loss", 0) > 0:
            self.successful_trades += 1

        profit_loss = Decimal(str(trade_data.get("profit_loss", 0)))
        self.total_profit_loss += profit_loss

        logger.info(f"Trade executed: {trade_data}")

        # Log to database
        from apps.bots.models import BotOrder

        BotOrder.objects.create(
            user=self.user,
            pair=trade_data.get("symbol", ""),
            exchange=trade_data.get("exchange", ""),
            side=trade_data.get("side", ""),
            category=self.__class__.__name__.replace("TradingStrategy", "").lower(),
            order_type=trade_data.get("order_type", "market"),
            quantity=Decimal(str(trade_data.get("amount", 0))),
            price=Decimal(str(trade_data.get("price", 0))),
            executed_price=Decimal(str(trade_data.get("executed_price", 0))),
            exchange_order_id=trade_data.get("order_id", ""),
            status=trade_data.get("status", "pending"),
            profit_loss=profit_loss,
            fees=Decimal(str(trade_data.get("fees", 0))),
            description=trade_data.get("description", ""),
            details=trade_data.get("details", {}),
        )

    def log_activity(
        self, action: str, message: str, level: str = "info", data: Dict[str, Any] = None
    ):
        """Log strategy activity."""
        try:
            from apps.bots.models import BotExecutionLog

            BotExecutionLog.objects.create(
                user=self.user,
                bot_type=self.__class__.__name__.replace("TradingStrategy", "").lower(),
                bot_id=self.config.get("bot_id", ""),
                action=action,
                message=message,
                level=level,
                data=data or {},
            )

        except Exception as e:
            logger.error(f"Error logging activity: {e}")

    def handle_error(self, error: Exception, context: str = ""):
        """Handle strategy errors."""
        self.last_error = str(error)
        self.error_count += 1

        logger.error(f"Strategy error in {context}: {error}")
        self.log_activity(
            "error",
            f"Error in {context}: {error}",
            level="error",
            data={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
            },
        )

        # Stop strategy if too many errors
        if self.error_count >= self.max_errors:
            self.log_activity(
                "auto_stop", f"Strategy stopped due to too many errors: {self.error_count}"
            )
            self.stop()

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration."""
        required_fields = self.get_required_config_fields()
        for field in required_fields:
            if field not in config:
                raise TradingBotException(
                    message=f"Missing required config field: {field}", error_code="INVALID_CONFIG"
                )
        return True

    def get_required_config_fields(self) -> list:
        """Get list of required configuration fields."""
        return []

    def cleanup(self):
        """Cleanup resources when stopping."""
        pass

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(user={self.user.email}, running={self.is_running})"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(user_id={self.user.id}, "
            f"running={self.is_running}, config={self.config})"
        )
