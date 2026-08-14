"""
Technical indicator webhook views for async trading signals.

These views receive EMA, RSI, and BB values from TradingView webhooks
and update the BotEngine instance for that user/pair.

Flow:
1. TradingView fires webhook with indicator value
2. View looks up user + PairConfig
3. Finds or creates the BotEngine instance
4. Updates the indicator on the engine (engine.EMA = value)
5. Calls engine.startBot() to evaluate entry/exit conditions
"""

import json
import logging
import time
from threading import Lock

from asgiref.sync import sync_to_async
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("apps.indicators")

# In-memory engine registry (same as oldbybit.py pattern)
# Key: "{user_id}_{pair_symbol}_{exchange}" -> BotEngine instance
_engine_registry = {}

_engine_registry_lock = Lock()
_ENGINE_TTL = 3600  # 1 hour — engines older than this are evicted


def _resolve_webhook_user(request):
    """Resolve user from X-Webhook-Token header. Returns user or None."""
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError

    User = get_user_model()
    token = request.headers.get("X-Webhook-Token") or request.POST.get("webhook_token")
    if not token:
        return None
    try:
        return User.objects.get(webhook_token=token)
    except (User.DoesNotExist, ValidationError):
        return None


def _get_or_create_engine(user, pair_config, exchange_name):
    """Get existing engine or create a new one for this user/pair/exchange."""
    from apps.exchanges.models import ExchangeCredentials
    from apps.trading.engines.bot_engine import BotEngine

    pair_symbol = pair_config.pair_symbol
    key = f"{user.id}_{pair_symbol}_{exchange_name}"

    with _engine_registry_lock:
        # Evict stale engines
        now = time.time()
        stale_keys = [k for k, (eng, ts) in _engine_registry.items() if now - ts > _ENGINE_TTL]
        for k in stale_keys:
            del _engine_registry[k]
        if stale_keys:
            logger.info(f"Evicted {len(stale_keys)} stale engines from registry")

        # Check cache
        if key in _engine_registry:
            engine, _ = _engine_registry[key]
            engine.pair_config.update(_pair_config_to_dict(pair_config))
            _engine_registry[key] = (engine, now)  # update timestamp
            return engine

    # Build config dict (outside lock — DB call)
    try:
        credentials = ExchangeCredentials.objects.get(
            user=user, exchange_name=exchange_name, is_active=True
        )
        creds = credentials.get_decrypted_credentials()
    except ExchangeCredentials.DoesNotExist:
        logger.error(f"No credentials for {user.username} on {exchange_name}")
        return None

    config = {
        "bot_name": f"{user.username}_{pair_symbol}_{exchange_name}",
        "user_id": str(user.id),
        "strategy": "quantum_ai",
        "symbol": pair_symbol,
        "exchange_name": exchange_name,
        "api_key": creds.get("api_key", ""),
        "secret_key": creds.get("secret_key", ""),
        "passphrase": creds.get("passphrase", ""),
        "is_testnet": getattr(credentials, "is_testnet", False),
        "parameters": _pair_config_to_dict(pair_config),
    }

    engine = BotEngine(config)
    with _engine_registry_lock:
        _engine_registry[key] = (engine, time.time())

    logger.info(f"Created BotEngine for {key}")
    return engine


def _pair_config_to_dict(pair_config):
    """Convert PairConfig model to plain dict for BotEngine."""
    return {
        "pair_symbol": pair_config.pair_symbol,
        "quantity": pair_config.quantity or 0,
        "favor_levels": pair_config.favor_levels or 3,
        "against_levels": pair_config.against_levels or 3,
        "favor_level_qty": pair_config.favor_level_qty or 0,
        "against_level_qty": pair_config.against_level_qty or 0,
        "favor_level_difference": pair_config.favor_level_difference or 0.5,
        "against_level_difference": pair_config.against_level_difference or 0.5,
        "Order_Type": pair_config.Order_Type or "market",
        "Amount_Type": pair_config.Amount_Type or "dollar",
        "SLTP_Type": pair_config.SLTP_Type or "dollar",
        "Stop_Loss": pair_config.Stop_Loss,
        "Take_Profit": pair_config.Take_Profit,
        "RSI_Lower": pair_config.RSI_Lower or 30,
        "RSI_Upper": pair_config.RSI_Upper or 70,
        "RSI_Entry": pair_config.RSI_Entry,
        "BB_Entry": pair_config.BB_Entry,
        "EMA_RSI_Entry": pair_config.EMA_RSI_Entry,
        "EMA_BB_Entry": pair_config.EMA_BB_Entry,
        "BB_RSI_Entry": pair_config.BB_RSI_Entry,
        "EMA_BB_RSI_Entry": pair_config.EMA_BB_RSI_Entry,
        "BB_Exit": pair_config.BB_Exit,
        "RSI_Exit": pair_config.RSI_Exit,
        "EMA_RSI_Exit": pair_config.EMA_RSI_Exit,
        "EMA_BB_Exit": pair_config.EMA_BB_Exit,
        "BB_RSI_Exit": pair_config.BB_RSI_Exit,
        "EMA_BB_RSI_Exit": pair_config.EMA_BB_RSI_Exit,
        "SL_Exit": pair_config.SL_Exit,
    }


@method_decorator(csrf_exempt, name="dispatch")
class EMAIndicatorView(View):
    """Handle EMA webhook from TradingView. Updates engine.EMA then runs startBot()."""

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

            raw_data = request.body.decode("utf-8").strip('"')
            data = json.loads(raw_data)

            if "EMA200" not in data:
                return JsonResponse(
                    {"status": "error", "message": "EMA200 value is required"}, status=400
                )

            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "bybit")
            ema_value = float(data.get("EMA200"))

            if not pair_symbol:
                return JsonResponse({"status": "error", "message": "pair is required"}, status=400)

            from apps.bots.models import PairConfig

            try:
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except PairConfig.DoesNotExist:
                return JsonResponse(
                    {"status": "error", "message": f"Pair config for {pair_symbol} not found"},
                    status=404,
                )

            # Get or create engine, update EMA, run strategy
            engine = await sync_to_async(_get_or_create_engine)(user, pair_config, exchange)
            if engine is None:
                return JsonResponse(
                    {"status": "error", "message": "No exchange credentials found"}, status=404
                )

            engine.EMA = ema_value

            # Save indicator to DB
            await sync_to_async(self._save_indicator)(user, pair_symbol, engine)

            # Run strategy evaluation (checks all conditions and trades if met)
            await sync_to_async(engine.startBot)()

            return JsonResponse(
                {
                    "status": "success",
                    "message": f"EMA processed for {pair_symbol}",
                    "EMA": ema_value,
                    "current_side": engine.current_side,
                    "reason": engine.reason,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON format"}, status=400)
        except Exception as e:
            logger.error(f"Error in EMA webhook: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return JsonResponse({"status": "error", "message": "Internal server error"}, status=500)

    def _save_indicator(self, user, pair_symbol, engine):
        from apps.bots.models import Indicator

        Indicator.objects.create(
            Pair=pair_symbol,
            user=user,
            EMA=engine.EMA,
            RSI=engine.RSI,
            Prev_RSI=engine.PrevRSI,
            Color=engine.RSI_color or "",
            Prev_Color=engine.RSI_prev_color or "",
            BB=engine.BB or "",
        )


@method_decorator(csrf_exempt, name="dispatch")
class RSIIndicatorView(View):
    """Handle RSI webhook from TradingView.

    Updates engine.RSI/PrevRSI/colors then runs startBot().
    """

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

            raw_data = request.body.decode("utf-8").strip('"')
            data = json.loads(raw_data)

            if "RSI" not in data:
                return JsonResponse(
                    {"status": "error", "message": "RSI value is required"}, status=400
                )

            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "bybit")
            rsi_value = float(data.get("RSI"))
            prev_rsi = float(data.get("PrevRSI", rsi_value))
            color = data.get("color", "white")
            prev_color = data.get("prev_color", "white")

            if not pair_symbol:
                return JsonResponse({"status": "error", "message": "pair is required"}, status=400)

            from apps.bots.models import PairConfig

            try:
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except PairConfig.DoesNotExist:
                return JsonResponse(
                    {"status": "error", "message": f"Pair config for {pair_symbol} not found"},
                    status=404,
                )

            engine = await sync_to_async(_get_or_create_engine)(user, pair_config, exchange)
            if engine is None:
                return JsonResponse(
                    {"status": "error", "message": "No exchange credentials found"}, status=404
                )

            engine.RSI = rsi_value
            engine.PrevRSI = prev_rsi
            engine.RSI_color = color
            engine.RSI_prev_color = prev_color

            await sync_to_async(self._save_indicator)(user, pair_symbol, engine)
            await sync_to_async(engine.startBot)()

            return JsonResponse(
                {
                    "status": "success",
                    "message": f"RSI processed for {pair_symbol}",
                    "RSI": rsi_value,
                    "current_side": engine.current_side,
                    "reason": engine.reason,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON format"}, status=400)
        except Exception as e:
            logger.error(f"Error in RSI webhook: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return JsonResponse({"status": "error", "message": "Internal server error"}, status=500)

    def _save_indicator(self, user, pair_symbol, engine):
        from apps.bots.models import Indicator

        Indicator.objects.create(
            Pair=pair_symbol,
            user=user,
            EMA=engine.EMA,
            RSI=engine.RSI,
            Prev_RSI=engine.PrevRSI,
            Color=engine.RSI_color or "",
            Prev_Color=engine.RSI_prev_color or "",
            BB=engine.BB or "",
        )


@method_decorator(csrf_exempt, name="dispatch")
class BollingerBandsView(View):
    """Handle Bollinger Bands webhook from TradingView. Updates engine.BB then runs startBot()."""

    async def post(self, request):
        try:
            user = await sync_to_async(_resolve_webhook_user)(request)
            if user is None:
                return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

            raw_data = request.body.decode("utf-8").strip('"')
            data = json.loads(raw_data)

            if "BB" not in data:
                return JsonResponse(
                    {"status": "error", "message": "BB value is required"}, status=400
                )

            pair_symbol = data.get("pair")
            exchange = data.get("exchange", "bybit")
            bb_signal = data.get("BB")

            if not pair_symbol:
                return JsonResponse({"status": "error", "message": "pair is required"}, status=400)

            from apps.bots.models import PairConfig

            try:
                pair_config = await sync_to_async(PairConfig.objects.get)(
                    user=user, pair_symbol=pair_symbol
                )
            except PairConfig.DoesNotExist:
                return JsonResponse(
                    {"status": "error", "message": f"Pair config for {pair_symbol} not found"},
                    status=404,
                )

            engine = await sync_to_async(_get_or_create_engine)(user, pair_config, exchange)
            if engine is None:
                return JsonResponse(
                    {"status": "error", "message": "No exchange credentials found"}, status=404
                )

            engine.BB = bb_signal

            await sync_to_async(self._save_indicator)(user, pair_symbol, engine)
            await sync_to_async(engine.startBot)()

            return JsonResponse(
                {
                    "status": "success",
                    "message": f"Bollinger Bands processed for {pair_symbol}",
                    "BB": bb_signal,
                    "current_side": engine.current_side,
                    "reason": engine.reason,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON format"}, status=400)
        except Exception as e:
            logger.error(f"Error in Bollinger Bands webhook: {type(e).__name__}: {e}")
            logger.debug("Full traceback", exc_info=True)
            return JsonResponse({"status": "error", "message": "Internal server error"}, status=500)

    def _save_indicator(self, user, pair_symbol, engine):
        from apps.bots.models import Indicator

        Indicator.objects.create(
            Pair=pair_symbol,
            user=user,
            EMA=engine.EMA,
            RSI=engine.RSI,
            Prev_RSI=engine.PrevRSI,
            Color=engine.RSI_color or "",
            Prev_Color=engine.RSI_prev_color or "",
            BB=engine.BB or "",
        )
