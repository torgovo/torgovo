"""
Webhook views for TradingView and Technical Indicators
"""

import hmac
import logging
from datetime import datetime, timezone

from django.core.cache import cache
from django.db.models import Sum
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import get_client_ip

logger = logging.getLogger(__name__)


# Field-name aliases accepted for the trading pair, so the same endpoint works
# with TradingView ("Pair") and any other alert platform that posts JSON
# (lowercase "pair", "symbol", "ticker", "market", "currency"). First key found
# wins; the generated template uses "Pair" but a hand-built body may use any.
PAIR_FIELD_ALIASES = ("Pair", "pair", "symbol", "ticker", "market", "currency")

# Side aliases across platforms: "buy"/"sell" (TradingView {{strategy.order.action}}),
# plus "long"/"short" used by many alert services. Any other value is rejected by
# the buy/sell validation in post().
SIDE_ALIASES = {"buy": "buy", "long": "buy", "sell": "sell", "short": "sell"}


def _extract_pair(payload: dict) -> str | None:
    """Return the trading pair from any of the common alert-platform field names."""
    for key in PAIR_FIELD_ALIASES:
        value = payload.get(key)
        if value:
            return value
    return None


def _extract_side(payload: dict) -> str | None:
    """Normalize the alert side to buy/sell, accepting common platform synonyms.

    Reads from "side", "action", or "direction"; maps "long"->buy and "short"->sell.
    Returns the raw (lowercased) value if unrecognized so post() can reject it.
    """
    side = payload.get("side") or payload.get("action") or payload.get("direction")
    if side is None:
        return None
    side = str(side).lower()
    return SIDE_ALIASES.get(side, side)


def _parse_alert_timestamp(raw: str) -> datetime | None:
    """Parse an alert timestamp — ISO 8601 (TradingView {{timenow}}) or Unix ms.

    Also tolerates {{time}} (TradingView epoch-seconds) and the ISO/epoch formats
    emitted by most other webhook platforms. Returns timezone-aware datetime in
    UTC, or None if unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip().strip('"').strip("'")
    # ISO 8601:  2026-06-21T12:34:56Z  or  2026-06-21T12:34:56.123Z
    try:
        if raw.endswith("Z"):
            raw_clean = raw[:-1]
            if "." in raw_clean:
                dt = datetime.strptime(raw_clean, "%Y-%m-%dT%H:%M:%S.%f")
            else:
                dt = datetime.strptime(raw_clean, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # Unix epoch milliseconds
    try:
        ms = int(raw)
        if 1_000_000_000_000 < ms < 2_000_000_000_000:  # sanity: 2001-2033
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    return None


def _webhook_fail_key(bot_id: str) -> str:
    return f"webhook:fail:{bot_id}"


def _webhook_dedupe_key(order_id: str) -> str:
    return f"webhook:dedupe:oid:{order_id}"


def _ip_fail_key(ip: str) -> str:
    return f"webhook:ip:fail:{ip}"


def _ip_bot_lock_key(ip: str, bot_id: str) -> str:
    return f"webhook:ip:lock:{ip}:{bot_id}"


RATE_LIMIT_FAILURES = 5
RATE_LIMIT_WINDOW = 300  # 5 minutes
TIMESTAMP_MAX_AGE = 120  # seconds
IP_LOCK_BOT_LIMIT = 3  # lock IP if it gets this many bot_ids banned
IP_LOCK_TTL = 600  # IP-wide ban duration (seconds)


def _record_failure(bot_id: str, ip: str = ""):
    """Increment webhook failure count for rate limiting."""
    key = _webhook_fail_key(bot_id)
    if not cache.add(key, 1, RATE_LIMIT_WINDOW):
        cache.incr(key, 1)
        cache.touch(key, RATE_LIMIT_WINDOW)
    if ip:
        ip_key = _ip_fail_key(ip)
        cache.add(ip_key, 0, RATE_LIMIT_WINDOW)
        cache.incr(ip_key, 1)
        cache.touch(ip_key, RATE_LIMIT_WINDOW)


def _validate_hmac_signature(raw_body: str, signature: str, secret: str) -> bool:
    """Validate HMAC-SHA256 signature of the raw request body."""
    import hashlib
    import hmac as _hmac

    expected = _hmac.new(
        secret.encode("utf-8"),
        raw_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return _hmac.compare_digest(expected, signature)


@method_decorator(csrf_exempt, name="dispatch")
class SignalBotWebhookView(APIView):
    """
    Global webhook endpoint for Signal Bot — works with TradingView or any
    platform that can POST a JSON body.
    URL: /api/webhooks/custombot/ (per-bot routed by bot_id in the payload)

    Authentication (choose one):
    1. HMAC mode (preferred): Provide X-Signature header with HMAC-SHA256
       hex digest of the raw request body, computed with the bot's secret_key.
       The 'secret' field is NOT required in the payload.
    2. Body-secret mode (any platform, incl. TradingView; required there since
       alert webhooks cannot send custom headers): Provide 'secret' in the JSON
       payload (constant-time comparison). No credentials -> 401; wrong -> 403.

    Required payload fields: bot_id, secret (unless HMAC used), side, timestamp
    Pair (or any alias: pair/symbol/ticker/market/currency)
    Optional: position_size, order_id
    """

    # AllowAny intentional — auth is via HMAC signature (X-Signature header) or
    # secret field in payload, verified in post() before any trade execution.
    permission_classes = [AllowAny]
    throttle_scope = "webhook"

    def post(self, request):
        """
        Handle incoming webhook from TradingView or any JSON-capable platform
        and execute a trade via CCXT. Required: bot_id, side, timestamp, Pair
        (or alias). Optional: position_size, secret (legacy), order_id.
        """
        import math

        from django.utils import timezone

        from apps.bots.models import SignalBot

        try:
            ip = get_client_ip(request)

            # Capture raw body BEFORE any parsing (needed for HMAC validation)
            raw_body = request.body.decode("utf-8")

            # Parse payload (handle both JSON and string-wrapped JSON)
            raw_data = raw_body.strip('"')
            if raw_data.startswith("{"):
                import json

                payload = json.loads(raw_data)
            else:
                payload = request.data

            safe_payload = {k: v for k, v in payload.items() if k != "secret"}
            logger.info(f"Received webhook payload: {safe_payload}")

            # Validate required fields (platform-agnostic alias extraction)
            bot_id = payload.get("bot_id")
            side = _extract_side(payload) or ""
            trading_pair = _extract_pair(payload)

            if not bot_id:
                return Response(
                    {"error": "Missing bot_id in payload"}, status=status.HTTP_400_BAD_REQUEST
                )

            # IP-wide ban: if this IP has been locked out entirely
            ip_ban_key = _ip_fail_key(ip)
            ip_fails = cache.get(ip_ban_key, 0)
            if ip_fails >= RATE_LIMIT_FAILURES * IP_LOCK_BOT_LIMIT:
                logger.warning(f"IP {ip} banned ({ip_fails} failures)")
                return Response(
                    {"error": "Too many failed attempts"}, status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Rate limit check: too many recent validation failures for this bot_id
            fail_count = cache.get(_webhook_fail_key(bot_id), 0)
            if fail_count >= RATE_LIMIT_FAILURES:
                logger.warning(
                    f"Bot {bot_id} rate-limited ({fail_count} failures in {RATE_LIMIT_WINDOW}s)"
                )
                return Response(
                    {"error": "Too many failed attempts"}, status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Timestamp validation (replay window)
            ts_raw = payload.get("timestamp")
            if not ts_raw:
                _record_failure(bot_id, ip)
                logger.warning(f"Missing timestamp for bot {bot_id}")
                return Response({"error": "Missing timestamp"}, status=status.HTTP_400_BAD_REQUEST)

            ts_dt = _parse_alert_timestamp(str(ts_raw))
            if ts_dt is None:
                _record_failure(bot_id, ip)
                logger.warning(f"Unparseable timestamp for bot {bot_id}: {ts_raw}")
                return Response({"error": "Invalid timestamp"}, status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now()
            age = (now - ts_dt).total_seconds()
            if abs(age) > TIMESTAMP_MAX_AGE:
                _record_failure(bot_id, ip)
                logger.warning(f"Timestamp too old for bot {bot_id}: {age:.0f}s")
                return Response({"error": "Timestamp expired"}, status=status.HTTP_400_BAD_REQUEST)

            # Find bot by bot_id (plan chain joined for the Model C quota below)
            try:
                bot = SignalBot.objects.select_related(
                    "user",
                    "subscription",
                    "subscription__plan",
                    "subscription__plan__subscription_plan",
                ).get(
                    bot_id=bot_id,
                    is_deleted=False,
                )
            except SignalBot.DoesNotExist:
                _record_failure(bot_id, ip)
                logger.warning(f"Invalid bot_id: {bot_id}")
                return Response(
                    {"error": "Invalid bot_id or secret"}, status=status.HTTP_403_FORBIDDEN
                )

            # Authenticate using the bot's unique per-bot secret key.
            # TradingView alert webhooks can ONLY POST a JSON body (they cannot
            # send HTTP headers), so the secret_key embedded in the bot's
            # generated webhook message is the primary credential. Callers that
            # can set headers may instead send the HMAC-SHA256 signature of the
            # raw body via X-Signature (no secret travels in the body).
            signature = request.META.get("HTTP_X_SIGNATURE", "")
            if signature:
                # HMAC path (optional) — validate against bot.secret_key.
                if not _validate_hmac_signature(raw_body, signature, bot.secret_key or ""):
                    _record_failure(bot_id, ip)
                    logger.warning(f"Invalid HMAC signature for bot {bot_id}")
                    return Response(
                        {"error": "Invalid bot_id or secret"}, status=status.HTTP_403_FORBIDDEN
                    )
            else:
                # TradingView path — the per-bot secret_key arrives in the body.
                # Constant-time compare: a guessed secret leaks no timing signal.
                body_secret = payload.get("secret")
                if not body_secret:
                    _record_failure(bot_id, ip)
                    logger.warning(f"No credentials for bot {bot_id} (no header, no body secret)")
                    return Response(
                        {"error": "Missing X-Signature header or body secret"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                if not hmac.compare_digest(str(body_secret), bot.secret_key or ""):
                    _record_failure(bot_id, ip)
                    logger.warning(f"Invalid body secret for bot {bot_id}")
                    return Response(
                        {"error": "Invalid bot_id or secret"}, status=status.HTTP_403_FORBIDDEN
                    )

            # Extract order_id from TradingView's {{strategy.order.id}} for dedup
            order_id = payload.get("order_id") or payload.get("strategy.order.id")
            if order_id:
                dedupe_key = _webhook_dedupe_key(str(order_id))
            else:
                import hashlib

                fallback_raw = (
                    f"{bot_id}|{ts_raw}|{side}|{trading_pair}|{payload.get('position_size', '')}"
                )
                dedupe_key = (
                    f"webhook:dedupe:fallback:"
                    f"{hashlib.sha256(fallback_raw.encode()).hexdigest()[:24]}"
                )

            if not cache.add(dedupe_key, "1", TIMESTAMP_MAX_AGE):
                logger.info(f"Dedupe hit for bot {bot_id}: {dedupe_key[:40]}… — ignoring replay")
                return Response(
                    {"success": True, "message": "Duplicate ignored"}, status=status.HTTP_200_OK
                )

            # Long-lived processed-order check (survives dedup cache expiry)
            if order_id:
                processed_key = f"webhook:processed:oid:{order_id}"
                if cache.get(processed_key):
                    logger.info(
                        f"Order {order_id} already processed (long-term dedup) for bot {bot_id}"
                    )
                    return Response(
                        {"success": True, "message": "Already processed"}, status=status.HTTP_200_OK
                    )

            user = bot.user

            # Validate bot is active
            if not bot.is_active:
                logger.info(f"Bot {bot_id} is not active")
                return Response({"error": "Bot is not active"}, status=status.HTTP_403_FORBIDDEN)

            # Validate subscription is active
            if bot.subscription and bot.subscription.status != "active":
                logger.info(f"Bot {bot_id} subscription is {bot.subscription.status}")
                return Response(
                    {"error": f"Subscription is {bot.subscription.status}"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # FR A2 Model C quota: signals/month is a PLAN-level entitlement,
            # counted across all of the user's signal bots (sum of the same
            # per-bot counters, reset monthly by reset_monthly_signal_limits).
            # Runs BEFORE the legacy block: Model C bots always have a
            # subscription, so `not bot.subscription` never fires for them;
            # legacy subs have plan.subscription_plan=NULL and skip this
            # branch — the subscribed-legacy bypass stays byte-stable.
            model_c_plan = None
            if bot.subscription and bot.subscription.plan:
                model_c_plan = bot.subscription.plan.subscription_plan
            if model_c_plan is not None:
                used = (
                    SignalBot.objects.filter(user=bot.user, is_deleted=False).aggregate(
                        total=Sum("signals_used_this_month")
                    )["total"]
                    or 0
                )
                plan_limit = model_c_plan.max_signals_per_month
                if used >= plan_limit:
                    logger.info(
                        f"User {bot.user_id} Model C signal limit reached "
                        f"({used}/{plan_limit}, plan {model_c_plan.slug})"
                    )
                    return Response(
                        {"error": "Monthly signal limit reached"},
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

            # Signal limit enforcement: free users get `signal_limit` per month
            if bot.signals_used_this_month >= bot.signal_limit and not bot.subscription:
                logger.info(
                    f"Bot {bot_id} signal limit reached "
                    f"({bot.signals_used_this_month}/{bot.signal_limit})"
                )
                return Response(
                    {"error": "Monthly signal limit reached"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            # Validate side
            if side not in ["buy", "sell"]:
                return Response(
                    {"error": "Invalid side, must be buy or sell"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get trading pair
            if not trading_pair:
                trading_pair = bot.trading_pair

            if not trading_pair:
                return Response(
                    {"error": "No trading pair specified"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Determine position size
            position_size = None
            if bot.use_tradingView_position_size:
                position_size = payload.get("position_size")
                if not position_size:
                    return Response(
                        {"error": "TradingView position size enabled but not provided"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    position_size = float(position_size)
                    if position_size < 0:
                        position_size = math.fabs(position_size)
                    if not position_size or position_size == 0:
                        position_size = float(bot.default_amount)
                except (ValueError, TypeError):
                    return Response(
                        {"error": "Invalid position size format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                position_size = float(bot.default_amount)

            # Execute the trade
            trade_result = self.execute_trade(
                user=user,
                bot=bot,
                exchange_name=bot.exchange_name,
                side=side,
                trading_pair=trading_pair,
                position_size=position_size,
            )

            if trade_result.get("status") == "error":
                logger.warning(
                    f"Trade execution failed for bot {bot_id}: {trade_result.get('message')}"
                )
                _record_failure(bot_id, ip)
                return Response(
                    {"error": "Trade execution failed"}, status=status.HTTP_502_BAD_GATEWAY
                )

            # Track as processed for long-term dedup (survives cache eviction of short dedup key)
            if order_id:
                cache.set(f"webhook:processed:oid:{order_id}", bot_id, 86400)

            # Update bot statistics
            bot.last_triggered = timezone.now()
            bot.total_trades += 1
            bot.signals_used_this_month += 1
            if trade_result.get("order_id"):
                bot.last_error = ""  # clear any prior error
            bot.save()

            logger.info(f"Trade executed for bot {bot_id}: {side} {position_size} {trading_pair}")

            return Response(
                {
                    "success": True,
                    "message": f"Trade executed: {side} {position_size} of {trading_pair}",
                    "trade_details": trade_result,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            # SECURITY: never echo internal exception strings to clients —
            # they can include CCXT API error messages, credential fragments,
            # or DB schema details. ``exc_info`` removed here because local
            # frames carry decrypted ``api_key``/``secret_key`` variables
            # (see execute_trade above).
            logger.error(f"Webhook processing error: {type(e).__name__}: {e}")
            return Response({"error": "Server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def execute_trade(self, user, bot, exchange_name, side, trading_pair, position_size):
        """
        Execute trade using CCXT for the specified exchange
        Supports: Binance, Bybit, OKX, MEXC, and others
        """
        import ccxt

        from apps.exchanges.models import ExchangeCredentials

        try:
            # Get exchange credentials
            try:
                credentials = ExchangeCredentials.objects.get(
                    user=user, exchange_name=exchange_name, is_active=True
                )
            except ExchangeCredentials.DoesNotExist:
                raise ValueError(f"{exchange_name} API credentials not configured")

            # Get decrypted credentials
            creds = credentials.get_decrypted_credentials()
            api_key = creds["api_key"]
            secret_key = creds["secret_key"]
            passphrase = creds.get("passphrase")

            # Initialize CCXT exchange
            exchange_class = getattr(ccxt, exchange_name.lower(), None)
            if not exchange_class:
                raise ValueError(f"Exchange {exchange_name} not supported by CCXT")

            exchange_config = {
                "apiKey": api_key,
                "secret": secret_key,
                "enableRateLimit": True,
            }

            if passphrase:
                exchange_config["password"] = passphrase

            # Create exchange instance
            exchange_instance = exchange_class(exchange_config)

            # SECURITY: zero out credentials from local scope immediately
            # after the exchange object has been initialized.  The exchange
            # holds its own copy; we must not keep secrets in locals that
            # could be captured by traceback machinery on a subsequent error.
            del api_key, secret_key, passphrase, creds, exchange_config

            # Load markets
            exchange_instance.load_markets()

            if trading_pair not in exchange_instance.markets:
                return {
                    "status": "error",
                    "message": f"Trading pair {trading_pair} not available on {exchange_name}",
                }

            # Get current price
            current_price = float(exchange_instance.fetch_ticker(trading_pair)["last"])

            # Convert position size to coins if not using TradingView position size
            if not bot.use_tradingView_position_size:
                # position_size is in USDT, convert to coins
                position_size = round(position_size / current_price, 8)

            # Execute market order
            order = exchange_instance.create_order(
                symbol=trading_pair,
                type="market",
                side=side,
                amount=position_size,
                price=current_price,
            )

            logger.info(f"{side.upper()} order executed: {order}")

            return {
                "status": "success",
                "order_id": order.get("id"),
                "timestamp": order.get("timestamp"),
                "amount": order.get("amount"),
                "price": order.get("price"),
                "cost": order.get("cost"),
                "exchange": exchange_name,
            }

        except Exception as e:
            # See note on the outer handler — do not include exc_info here:
            # ``api_key`` / ``secret_key`` / ``passphrase`` are local
            # variables of ``execute_trade`` and would be captured by the
            # traceback machinery.
            logger.error(f"Trade execution error: {type(e).__name__}: {e}")
            return {"status": "error", "message": "Trade execution failed"}
