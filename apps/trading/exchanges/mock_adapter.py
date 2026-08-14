"""
Mock Exchange Adapter

Simulates a full exchange in-memory (orders, balances, prices).
No network access required. Use for exchanges that don't provide
an API sandbox (MEXC, Coinbase) or for offline testing.

PURE PYTHON - NO DJANGO IMPORTS
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .base_adapter import BaseAdapter

logger = logging.getLogger("trading.exchanges")


class MockAdapter(BaseAdapter):
    """Simulated exchange adapter for testing without real API access."""

    def __init__(self, credentials: Dict[str, str], demo_mode: bool = False):
        self.demo_mode = True  # Mock is always demo
        self.credentials = credentials or {}
        self.exchange_name_value = credentials.get("exchange_name", "mock")
        self._lock = threading.Lock()

        initial_usdt = float(credentials.get("initial_balance", 10000))
        self._balances = {"USDT": {"free": initial_usdt, "used": 0.0, "total": initial_usdt}}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._prices: Dict[str, float] = {
            "BTC/USDT": 65000.0,
            "ETH/USDT": 3500.0,
            "SOL/USDT": 145.0,
            "BNB/USDT": 580.0,
            "ADA/USDT": 0.45,
            "DOT/USDT": 7.20,
            "LINK/USDT": 14.50,
            "AVAX/USDT": 35.0,
        }
        self._trades: List[Dict[str, Any]] = []
        self.rate_limit_delay = 0.0
        self.max_retries = 1

    @property
    def exchange_name(self) -> str:
        return self.exchange_name_value

    def _initialize_exchange(self):
        return None

    def _make_request(self, method: str, *args, **kwargs):
        return getattr(self, f"_mock_{method}", lambda *a, **kw: {})(*args, **kwargs)

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    def _generate_price(self, symbol: str) -> float:
        base = self._prices.get(symbol, 100.0)
        jitter = base * 0.001
        return base + (hash(time.time()) % 100 - 50) / 50 * jitter

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        price = self._generate_price(symbol)
        return {
            "symbol": symbol,
            "last": price,
            "bid": price * 0.999,
            "ask": price * 1.001,
            "high": price * 1.02,
            "low": price * 0.98,
            "volume": 1000.0,
            "quote_volume": 1000.0 * price,
            "change_24h": price * 0.01,
            "percentage_24h": 1.0,
            "timestamp": int(time.time() * 1000),
        }

    def get_current_price(self, symbol: str) -> float:
        return self._generate_price(symbol)

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[Dict[str, Any]]:
        price = self._prices.get(symbol, 100.0)
        now = int(time.time()) * 1000
        tf_ms = {
            "1m": 60000,
            "5m": 300000,
            "15m": 900000,
            "1h": 3600000,
            "4h": 14400000,
            "1d": 86400000,
        }
        interval = tf_ms.get(timeframe, 3600000)
        candles = []
        for i in range(limit):
            ts = now - (limit - i) * interval
            jitter = price * 0.002 * (hash(str(ts)) % 100 - 50) / 50
            o = price + jitter
            h = o * 1.01
            low = o * 0.99
            c = o * (1 + 0.001 * (hash(str(ts + 1)) % 100 - 50) / 50)
            candles.append(
                {
                    "timestamp": ts,
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": c,
                    "volume": 100.0 + abs(hash(str(ts)) % 1000),
                }
            )
        return candles

    def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        price = self._prices.get(symbol, 100.0)
        bids = [
            [price * (1 - 0.001 * i), 1.0 + abs(hash(str(i))) % 10] for i in range(1, limit + 1)
        ]
        asks = [
            [price * (1 + 0.001 * i), 1.0 + abs(hash(str(-i))) % 10] for i in range(1, limit + 1)
        ]
        return {"symbol": symbol, "bids": bids, "asks": asks, "timestamp": int(time.time() * 1000)}

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def fetch_balance(self) -> Dict[str, Any]:
        with self._lock:
            total = {}
            free = {}
            used = {}
            for ccy, bal in self._balances.items():
                total[ccy] = bal["total"]
                free[ccy] = bal["free"]
                used[ccy] = bal["used"]
            return {
                "total": dict(total),
                "free": dict(free),
                "used": dict(used),
                "timestamp": int(time.time() * 1000),
            }

    def _credit(self, currency: str, amount: float):
        if currency not in self._balances:
            self._balances[currency] = {"free": 0.0, "used": 0.0, "total": 0.0}
        self._balances[currency]["free"] += amount
        self._balances[currency]["total"] += amount

    def _debit(self, currency: str, amount: float):
        bal = self._balances.get(currency, {"free": 0.0, "used": 0.0, "total": 0.0})
        bal["free"] -= amount
        bal["total"] -= amount
        self._balances[currency] = bal

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        price = self._generate_price(symbol)
        base, quote = symbol.split("/")
        cost = amount * price

        with self._lock:
            if side.lower() == "buy":
                if self._balances.get(quote, {}).get("free", 0) < cost:
                    raise ValueError(f"Insufficient {quote} balance")
                self._debit(quote, cost)
                self._credit(base, amount)
            else:
                if self._balances.get(base, {}).get("free", 0) < amount:
                    raise ValueError(f"Insufficient {base} balance")
                self._debit(base, amount)
                self._credit(quote, cost)

            order_id = uuid.uuid4().hex[:16]
            order = {
                "id": order_id,
                "client_order_id": None,
                "symbol": symbol,
                "side": side.lower(),
                "type": "market",
                "amount": amount,
                "price": price,
                "filled": amount,
                "remaining": 0.0,
                "cost": cost,
                "status": "closed",
                "timestamp": int(time.time() * 1000),
                "fee": {"cost": cost * 0.001, "currency": quote},
            }
            self._orders[order_id] = order
            self._trades.append(order)
            return dict(order)

    def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        base, quote = symbol.split("/")
        cost = amount * price

        with self._lock:
            if side.lower() == "buy":
                if self._balances.get(quote, {}).get("free", 0) < cost:
                    raise ValueError(f"Insufficient {quote} balance")
                self._debit(quote, cost)
            else:
                if self._balances.get(base, {}).get("free", 0) < amount:
                    raise ValueError(f"Insufficient {base} balance")
                self._debit(base, amount)

            order_id = uuid.uuid4().hex[:16]
            order = {
                "id": order_id,
                "client_order_id": None,
                "symbol": symbol,
                "side": side.lower(),
                "type": "limit",
                "amount": amount,
                "price": price,
                "filled": 0.0,
                "remaining": amount,
                "cost": 0.0,
                "status": "open",
                "timestamp": int(time.time() * 1000),
                "fee": {"cost": 0, "currency": quote},
            }
            self._orders[order_id] = order
            return dict(order)

    def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        order_id = uuid.uuid4().hex[:16]
        base, quote = symbol.split("/")
        order = {
            "id": order_id,
            "client_order_id": None,
            "symbol": symbol,
            "side": side.lower(),
            "type": "stop_loss",
            "amount": amount,
            "price": stop_price,
            "filled": 0.0,
            "remaining": amount,
            "cost": 0.0,
            "status": "open",
            "stop_price": stop_price,
            "timestamp": int(time.time() * 1000),
            "fee": {"cost": 0, "currency": quote},
        }
        with self._lock:
            self._orders[order_id] = order
        return dict(order)

    def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        take_profit_price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        order_id = uuid.uuid4().hex[:16]
        base, quote = symbol.split("/")
        order = {
            "id": order_id,
            "client_order_id": None,
            "symbol": symbol,
            "side": side.lower(),
            "type": "take_profit",
            "amount": amount,
            "price": take_profit_price,
            "filled": 0.0,
            "remaining": amount,
            "cost": 0.0,
            "status": "open",
            "take_profit_price": take_profit_price,
            "timestamp": int(time.time() * 1000),
            "fee": {"cost": 0, "currency": quote},
        }
        with self._lock:
            self._orders[order_id] = order
        return dict(order)

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                raise ValueError(f"Order {order_id} not found")
            return dict(order)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                dict(o)
                for o in self._orders.values()
                if o["status"] == "open" and (symbol is None or o["symbol"] == symbol)
            ]

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                raise ValueError(f"Order {order_id} not found")
            order["status"] = "canceled"
            base, quote = symbol.split("/")
            if order["side"] == "buy":
                self._credit(quote, order["remaining"] * order["price"])
            else:
                self._credit(base, order["remaining"])
            return {"id": order_id, "symbol": symbol, "cancelled": True}

    def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        open_orders = self.fetch_open_orders(symbol)
        results = []
        for o in open_orders:
            results.append(self.cancel_order(o["id"], symbol))
        return results

    def create_market_order_with_cost(
        self, symbol: str, side: str, cost: float, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        price = self.get_current_price(symbol)
        amount = cost / price if price > 0 else cost
        return self.create_market_order(symbol, side, amount, params)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            positions = list(self._positions.values())
            if symbol:
                positions = [p for p in positions if p["symbol"] == self.format_symbol(symbol)]
            return [dict(p) for p in positions if float(p.get("contracts", 0)) != 0]

    def close_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        return self.create_market_order(
            symbol, "sell" if side.lower() == "long" else "buy", amount, {"reduceOnly": True}
        )

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    def format_symbol(self, symbol: str) -> str:
        return symbol

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        return round(amount, 8)

    def price_to_precision(self, symbol: str, price: float) -> float:
        return round(price, 2)

    def is_order_filled(self, order: Dict[str, Any]) -> bool:
        return order.get("status") == "closed"

    def is_order_open(self, order: Dict[str, Any]) -> bool:
        return order.get("status") == "open"

    def get_minimum_order_amount(self, symbol: str) -> float:
        return 0.0001

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "balance": self.fetch_balance(),
            "exchange": self.exchange_name,
            "demo_mode": True,
        }

    def fetch_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        positions = self.fetch_positions(symbol)
        if positions:
            return positions[0]
        return {
            "symbol": self.format_symbol(symbol),
            "side": None,
            "contracts": 0,
            "entry_price": 0,
            "unrealized_pnl": 0,
        }

    def set_market_type(self, market_type: str = "spot"):
        pass

    def execute_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        action = signal.get("action", "").lower()
        symbol = signal.get("symbol")
        amount = signal.get("amount", 0)
        price = signal.get("price")
        order_type = signal.get("type", "market").lower()
        stop_price = signal.get("stop_price")
        take_profit_price = signal.get("take_profit_price")

        if not action or not symbol or not amount:
            raise ValueError("Signal must contain 'action', 'symbol', and 'amount'")

        if stop_price:
            return self.create_stop_loss_order(symbol, action, amount, stop_price)
        if take_profit_price:
            return self.create_take_profit_order(symbol, action, amount, take_profit_price)
        if order_type == "limit" and price:
            return self.create_limit_order(symbol, action, amount, price)
        return self.create_market_order(symbol, action, amount)
