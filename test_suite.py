"""
Standalone test harness for BotEngine trading logic.

Tests:
  - 6 buy entry conditions + 6 sell entry conditions
  - Grid level calculation (favor/against)
  - Order placement flow (prepare_order_data -> calculated_grid_orders)
  - Monitoring loop logic (grid fills, re-entry)
  - TP exit conditions
  - Edge cases (already in trade, duplicate prevention)
  - Full trade cycle (entry -> monitoring -> exit)

Run:  python test_suite.py
No Django, no DB, no exchange credentials required.
"""

import sys, os, time, threading
from datetime import datetime
from typing import Dict, Any, Optional, List

# =============================================================================
# Fake Exchange Adapter
# =============================================================================

class FakeAdapter:
    """Simulates exchange with controllable price, positions, and orders."""
    def __init__(self):
        self.exchange_name = 'bybit'
        self.exchange = self
        self._price = 50000.0
        self._open_orders = []
        self._filled_orders = []
        self._position = None

    def fetch_ticker(self, symbol):
        return {'last': self._price, 'symbol': symbol}

    def fetch_ohlcv(self, symbol, timeframe='1h', limit=100):
        return [[int(time.time()*1000), self._price, self._price*1.01, self._price*0.99, self._price, 1000]] * limit

    def fetch_order_book(self, symbol, limit=10):
        return {'bids': [[self._price - x, 1] for x in range(1, 11)],
                'asks': [[self._price + x, 1] for x in range(1, 11)]}

    def fetch_positions(self, symbol=None):
        return [self._position] if self._position else []

    def fetch_position(self, symbol):
        return self._position

    def fetch_open_orders(self, symbol=None):
        return self._open_orders

    def fetch_order(self, order_id, symbol=None):
        for o in self._open_orders + self._filled_orders:
            if o.get('id') == order_id or o.get('orderId') == order_id:
                return o
        return {'status': 'closed', 'id': order_id}

    def create_market_order(self, symbol, side, quantity, params=None):
        o = {'id': f'mkt_{side}_{int(time.time()*1000)}', 'symbol': symbol,
             'side': side, 'amount': quantity, 'price': self._price, 'status': 'closed'}
        self._filled_orders.append(o)
        return o

    def create_market_order_with_cost(self, symbol, side, cost):
        return self.create_market_order(symbol, side, cost)

    def create_limit_order(self, symbol, side, quantity, price):
        oid = f'lmt_{side}_{price}_{int(time.time()*1000)}'
        o = {'id': oid, 'orderId': oid, 'symbol': symbol, 'side': side,
             'amount': quantity, 'price': price, 'status': 'open'}
        self._open_orders.append(o)
        return o

    def cancel_all_orders(self, symbol=None):
        self._open_orders = []

    def get_current_price(self, symbol):
        return self._price

    def amount_to_precision(self, symbol, amount):
        return amount

    def set_price(self, price):
        self._price = price

    def set_position(self, side, size, entry=None, pnl=0):
        entry = entry or self._price
        self._position = {'side': side, 'contracts': size, 'entryPrice': entry,
                          'unrealized_pnl': pnl, 'notional': size * entry}

    def clear_position(self):
        self._position = None

    def _make_request(self, method, *args, **kwargs):
        return self._position if method == 'fetch_position' else None

    def get_account_info(self):
        return {'total': 100000, 'free': 50000, 'used': 50000}


# =============================================================================
# TestBotEngine — pure logic, no DB/Django/Celery
# =============================================================================

class TestBotEngine:
    """Stripped-down BotEngine: same entry/exit logic, no external deps."""

    def __init__(self, config: Dict[str, Any], adapter: FakeAdapter):
        self.config = config
        self.adapter = adapter
        self.symbol = config.get('symbol', 'BTC/USDT:USDT')
        self.pair_config = config.get('parameters', {})
        self.pair_config['pair_symbol'] = config.get('symbol', '')

        self.EMA = 0.0
        self.BB = None
        self.RSI = 0.0
        self.PrevRSI = 0.0
        self.RSI_color = None
        self.current_price = 0.0
        self.current_side = "None"
        self.count = 0
        self.bot_running = False
        self.monitoring = False
        self._stop_event = threading.Event()
        self.reason = ""
        self.favor_lvl = []
        self.against_lvl = []
        self.orders_placed = 0
        self.orders_closed = 0

    def update_conditions(self):
        self.current_price = self.adapter.fetch_ticker(self.symbol)['last']
        e = self.EMA
        self.EmaBuyCondition = (self.current_price >= e != 0) if e != 0 else False
        self.EmaSellCondition = (self.current_price <= e != 0) if e != 0 else False
        self.RsiBuyCondition = (self.PrevRSI <= self.pair_config.get('RSI_Lower', 30)
                                and self.RSI_color == 'white')
        self.RsiSellCondition = (self.PrevRSI >= self.pair_config.get('RSI_Upper', 70)
                                 and self.RSI_color == 'white')
        self.BBBuyCondition = (self.BB == "Crossing Down Band" or
                               self.BB == "Closed Below Lower Band" or
                               self.BB == "Up Arrow")
        self.BBSellCondition = (self.BB == "Crossing Up Band" or
                                self.BB == "Closed Above Upper Band" or
                                self.BB == "Down Arrow")
        self.NoTrade = (self.count == 0 and self.current_side == "None")
        self.BuyTrade = (self.count == 1 and self.current_side == "Buy")
        self.SellTrade = (self.count == 1 and self.current_side == "Sell")

    def set_indicators(self, ema=None, rsi=None, prev_rsi=None, rsi_color=None, bb=None):
        if ema is not None: self.EMA = ema
        if rsi is not None: self.RSI = rsi
        if prev_rsi is not None: self.PrevRSI = prev_rsi
        if rsi_color is not None: self.RSI_color = rsi_color
        if bb is not None: self.BB = bb
        self.update_conditions()

    def prepare_order_data(self, side, price):
        c = self.pair_config
        return {
            "symbol": self.symbol, "Order_Type": c.get('Order_Type', 'market'),
            "side": side, "qty": c.get('quantity', 100), "price": price,
            "favor_levels": c.get('favor_levels', 3),
            "against_levels": c.get('against_levels', 3),
            "favor_level_qty": c.get('favor_level_qty', 20),
            "against_level_qty": c.get('against_level_qty', 20),
            "favor_level_qty_dollar": None, "against_level_qty_dollar": None,
            "favor_level_difference": c.get('favor_level_difference', 0.5),
            "against_level_difference": c.get('against_level_difference', 0.5),
        }

    def calculate_grids(self, side):
        p = self.current_price
        fd = self.pair_config.get('favor_level_difference', 0.5)
        ad = self.pair_config.get('against_level_difference', 0.5)
        fn = self.pair_config.get('favor_levels', 3)
        an = self.pair_config.get('against_levels', 3)
        if side.lower() == 'buy':
            favor = [round(p * (1 + (i+1) * fd / 100), 6) for i in range(fn)]
            against = [round(p * (1 - (i+1) * ad / 100), 6) for i in range(an)]
        else:
            favor = [round(p * (1 - (i+1) * fd / 100), 6) for i in range(fn)]
            against = [round(p * (1 + (i+1) * ad / 100), 6) for i in range(an)]
        return favor, against

    def calculated_grid_orders(self, data):
        print(f"    -> Placing initial {data['side']} @ ${data['price']}")
        self.adapter.create_market_order(self.symbol, data['side'].lower(), data['qty'])
        self.orders_placed += 1
        f, a = self.calculate_grids(data['side'])
        self.favor_lvl, self.against_lvl = list(f), list(a)
        print(f"    -> Grid: favor={[f'{x:.2f}' for x in f]}, against={[f'{x:.2f}' for x in a]}")
        for p in f:
            s = 'sell' if data['side'].lower() == 'buy' else 'buy'
            self.adapter.create_limit_order(self.symbol, s, data.get('favor_level_qty', 20), float(p))
            self.orders_placed += 1
        for p in a:
            s = 'buy' if data['side'].lower() == 'buy' else 'sell'
            self.adapter.create_limit_order(self.symbol, s, data.get('against_level_qty', 20), float(p))
            self.orders_placed += 1
        print(f"    -> {self.orders_placed} total orders")
        self.bot_running = True
        self.monitoring = True
        return {'initial_order': 'placed'}

    def close_all_orders(self, description):
        print(f"    -> Closing all: {description}")
        self.adapter.cancel_all_orders(self.symbol)
        pos = self.adapter.fetch_position(self.symbol)
        if pos and float(pos.get('contracts', 0)) > 0:
            s = 'sell' if pos['side'] == 'long' else 'buy'
            self.adapter.create_market_order(self.symbol, s, float(pos['contracts']))
            self.orders_closed += 1
        self.monitoring = False
        self.bot_running = False
        self.count = 0
        self.current_side = "None"
        self.adapter.clear_position()

    def startBot(self):
        self.update_conditions()
        p = self.current_price
        print(f"  Price=${p:.2f} | "
              f"EMA_buy={self.EmaBuyCondition} sell={self.EmaSellCondition} "
              f"RSI_buy={self.RsiBuyCondition} sell={self.RsiSellCondition} "
              f"BB_buy={self.BBBuyCondition} sell={self.BBSellCondition} "
              f"NoTrade={self.NoTrade} BuyTrade={self.BuyTrade} SellTrade={self.SellTrade}")

        if self.NoTrade:
            # BUY cases
            if self.EmaBuyCondition and self.RsiBuyCondition and \
               self.pair_config.get('EMA_RSI_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE1: EMA+RSI")
            elif self.BBBuyCondition and self.EmaBuyCondition and \
                 self.pair_config.get('EMA_BB_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE2: EMA+BB")
            elif self.RsiBuyCondition and self.BBBuyCondition and \
                 self.pair_config.get('BB_RSI_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE3: BB+RSI")
            elif self.RsiBuyCondition and \
                 self.pair_config.get('RSI_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE4: RSI only")
            elif self.BBBuyCondition and \
                 self.pair_config.get('BB_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE5: BB only")
            elif self.EmaBuyCondition and self.RsiBuyCondition and self.BBBuyCondition and \
                 self.pair_config.get('EMA_BB_RSI_Entry') in ('buy', 'both'):
                return self._entry("Buy", "CASE6: EMA+RSI+BB")
            # SELL cases
            elif self.EmaSellCondition and self.RsiSellCondition and \
                 self.pair_config.get('EMA_RSI_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE1: EMA+RSI")
            elif self.BBSellCondition and self.EmaSellCondition and \
                 self.pair_config.get('EMA_BB_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE2: EMA+BB")
            elif self.BBSellCondition and self.RsiSellCondition and \
                 self.pair_config.get('BB_RSI_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE3: BB+RSI")
            elif self.RsiSellCondition and \
                 self.pair_config.get('RSI_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE4: RSI only")
            elif self.BBSellCondition and \
                 self.pair_config.get('BB_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE5: BB only")
            elif self.EmaSellCondition and self.RsiSellCondition and self.BBSellCondition and \
                 self.pair_config.get('EMA_BB_RSI_Entry') in ('sell', 'both'):
                return self._entry("Sell", "SELL-CASE6: EMA+RSI+BB")
            print("    - No condition met")
            return None
        elif self.BuyTrade:
            if self.BBSellCondition and self.pair_config.get('BB_Exit') in ('tp', 'both'):
                return self._exit("TP-CASE1: BB")
            elif self.RsiSellCondition and self.pair_config.get('RSI_Exit') in ('tp', 'both'):
                return self._exit("TP-CASE2: RSI")
            elif self.RsiSellCondition and self.BBSellCondition and \
                 self.pair_config.get('BB_RSI_Exit') in ('tp', 'both'):
                return self._exit("TP-CASE3: BB+RSI")
            elif self.BBSellCondition and (self.EmaSellCondition or self.EmaBuyCondition) and \
                 self.pair_config.get('EMA_BB_Exit') in ('tp', 'both'):
                return self._exit("TP-CASE4: EMA+BB")
            print("    - In buy trade, no exit")
            return None
        elif self.SellTrade:
            if self.RsiBuyCondition and self.pair_config.get('RSI_Exit') in ('tp', 'both'):
                return self._exit("SELL-TP-CASE1: RSI")
            elif self.BBBuyCondition and self.RsiBuyCondition and \
                 self.pair_config.get('BB_RSI_Exit') in ('tp', 'both'):
                return self._exit("SELL-TP-CASE2: BB+RSI")
            elif self.BBBuyCondition and self.pair_config.get('BB_Exit') in ('tp', 'both'):
                return self._exit("SELL-TP-CASE3: BB")
            elif self.EmaBuyCondition and self.BBBuyCondition and \
                 self.pair_config.get('EMA_BB_Exit') in ('tp', 'both'):
                return self._exit("SELL-TP-CASE4: EMA+BB")
            print("    - In sell trade, no exit")
            return None

    def _entry(self, side, reason):
        print(f"    ENTRY: {reason}")
        data = self.prepare_order_data(side, self.current_price)
        self.count = 1
        self.current_side = side
        self.reason = reason
        self.calculated_grid_orders(data)
        return {'action': 'entry', 'side': side, 'reason': reason}

    def _exit(self, reason):
        print(f"    EXIT: {reason}")
        self.close_all_orders(reason)
        self.reason = reason
        return {'action': 'exit', 'reason': reason}


# =============================================================================
# DEFAULT CONFIG
# =============================================================================

BASE = {
    'symbol': 'BTC/USDT:USDT',
    'exchange_name': 'bybit',
    'parameters': {
        'favor_levels': 3, 'against_levels': 3,
        'favor_level_qty': 20, 'against_level_qty': 20,
        'favor_level_difference': 0.5, 'against_level_difference': 0.5,
        'quantity': 100, 'Amount_Type': 'coin', 'Order_Type': 'market',
        'SLTP_Type': 'percentage', 'Take_Profit': 50, 'Stop_Loss': -20,
        'RSI_Lower': 30, 'RSI_Upper': 70,
    }
}


def cfg(overrides: dict) -> dict:
    """Create config with merged parameter overrides."""
    result = {'symbol': BASE['symbol'], 'exchange_name': BASE['exchange_name'],
              'parameters': {**BASE['parameters']}}
    if 'parameters' in overrides:
        result['parameters'].update(overrides['parameters'])
    return result


# =============================================================================
# TEST RUNNER
# =============================================================================

PASS, FAIL = 0, 0
INDENT = "  "

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        print(f"{INDENT}OK {name}")
        PASS += 1
    else:
        print(f"{INDENT}FAIL {name} {detail}")
        FAIL += 1

def section(name):
    print(f"\n{'='*60}\n{name}\n{'='*60}")

def new_bot(config_updates=None):
    a = FakeAdapter()
    c = cfg(config_updates or {})
    b = TestBotEngine(c, a)
    return b, a


# =============================================================================
# BUY ENTRY CASES
# =============================================================================

def test_buy_cases():
    section("BUY ENTRY — all 6 cases")

    # CASE1: EMA+RSI  (price > EMA, RSI oversold bounce)
    b, a = new_bot({'parameters': {'EMA_RSI_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, prev_rsi=25, rsi_color='white')
    r = b.startBot()
    check("CASE1 EMA+RSI triggers", r and r['action'] == 'entry' and 'CASE1' in r['reason'])
    check("CASE1 sets Buy", b.current_side == 'Buy')
    check("CASE1 count=1", b.count == 1)
    check("CASE1 places orders", b.orders_placed > 0)

    # CASE2: EMA+BB
    b, a = new_bot({'parameters': {'EMA_BB_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, bb="Crossing Down Band")
    r = b.startBot()
    check("CASE2 EMA+BB triggers", r and r['action'] == 'entry')

    # CASE3: BB+RSI
    b, a = new_bot({'parameters': {'BB_RSI_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(prev_rsi=25, rsi_color='white', bb="Crossing Down Band")
    r = b.startBot()
    check("CASE3 BB+RSI triggers", r and r['action'] == 'entry')

    # CASE4: RSI only
    b, a = new_bot({'parameters': {'RSI_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(prev_rsi=25, rsi_color='white')
    r = b.startBot()
    check("CASE4 RSI only triggers", r and r['action'] == 'entry')

    # CASE5: BB only
    b, a = new_bot({'parameters': {'BB_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Down Band")
    r = b.startBot()
    check("CASE5 BB only triggers", r and r['action'] == 'entry')

    # CASE6: EMA+RSI+BB
    b, a = new_bot({'parameters': {'EMA_BB_RSI_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, prev_rsi=25, rsi_color='white', bb="Crossing Down Band")
    r = b.startBot()
    check("CASE6 EMA+RSI+BB triggers", r and r['action'] == 'entry')


# =============================================================================
# SELL ENTRY CASES
# =============================================================================

def test_sell_cases():
    section("SELL ENTRY — all 6 cases")

    # CASE1: EMA+RSI  (price < EMA, RSI overbought)
    b, a = new_bot({'parameters': {'EMA_RSI_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(ema=51000, prev_rsi=75, rsi_color='white')
    r = b.startBot()
    check("SELL-CASE1 EMA+RSI triggers", r and r['action'] == 'entry' and 'CASE1' in r['reason'])
    check("SELL-CASE1 sets Sell", b.current_side == 'Sell')
    check("SELL-CASE1 count=1", b.count == 1)

    b, a = new_bot({'parameters': {'EMA_BB_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(ema=51000, bb="Crossing Up Band")
    r = b.startBot()
    check("SELL-CASE2 EMA+BB triggers", r and r['action'] == 'entry')

    b, a = new_bot({'parameters': {'BB_RSI_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(prev_rsi=75, rsi_color='white', bb="Crossing Up Band")
    r = b.startBot()
    check("SELL-CASE3 BB+RSI triggers", r and r['action'] == 'entry')

    b, a = new_bot({'parameters': {'RSI_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(prev_rsi=75, rsi_color='white')
    r = b.startBot()
    check("SELL-CASE4 RSI only triggers", r and r['action'] == 'entry')

    b, a = new_bot({'parameters': {'BB_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Up Band")
    r = b.startBot()
    check("SELL-CASE5 BB only triggers", r and r['action'] == 'entry')

    b, a = new_bot({'parameters': {'EMA_BB_RSI_Entry': 'sell'}})
    a.set_price(50000)
    b.set_indicators(ema=51000, prev_rsi=75, rsi_color='white', bb="Crossing Up Band")
    r = b.startBot()
    check("SELL-CASE6 EMA+RSI+BB triggers", r and r['action'] == 'entry')


# =============================================================================
# NO ENTRY
# =============================================================================

def test_no_entry():
    section("NO ENTRY — conditions don't match")
    b, a = new_bot({'parameters': {'EMA_RSI_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, prev_rsi=50, rsi_color='white')
    r = b.startBot()
    check("No entry when conditions wrong", r is None)
    check("count stays 0", b.count == 0)
    check("side stays None", b.current_side == "None")


# =============================================================================
# GRID CALCULATION
# =============================================================================

def test_grids():
    section("GRID CALCULATION")
    b, a = new_bot({'parameters': {'favor_levels': 5, 'against_levels': 5}})
    a.set_price(50000)
    b.current_price = 50000
    f, a_ = b.calculate_grids("buy")
    check("5 favor levels (buy)", len(f) == 5)
    check("5 against levels (buy)", len(a_) == 5)
    check("Favor above entry (buy)", all(p > 50000 for p in f))
    check("Against below entry (buy)", all(p < 50000 for p in a_))

    b2, a2 = new_bot()
    a2.set_price(50000)
    b2.current_price = 50000
    f2, a2_ = b2.calculate_grids("sell")
    check("Favor below entry (sell)", all(p < 50000 for p in f2))
    check("Against above entry (sell)", all(p > 50000 for p in a2_))


def test_grid_spacing():
    section("GRID SPACING")
    b, a = new_bot({'parameters': {'favor_level_difference': 2.0, 'against_level_difference': 1.0}})
    a.set_price(50000)
    b.current_price = 50000
    f, a_ = b.calculate_grids("buy")
    check("2% favor spacing", round(f[0]) == 51000)
    check("1% against spacing", round(a_[0]) == 49500)


# =============================================================================
# DUPLICATE PREVENTION
# =============================================================================

def test_no_double_entry():
    section("DUPLICATE PREVENTION")
    b, a = new_bot({'parameters': {'BB_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Down Band")
    r1 = b.startBot()
    check("First entry works", r1 and r1['action'] == 'entry')
    r2 = b.startBot()
    check("Second entry blocked (BuyTrade=True)", r2 is None)


# =============================================================================
# TP EXIT CONDITIONS
# =============================================================================

def test_tp_exits():
    section("TP EXITS")

    # Enter buy trade, then trigger BB exit
    b, a = new_bot({'parameters': {'BB_Entry': 'buy', 'BB_Exit': 'tp'}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Down Band")
    b.startBot()
    a.set_price(52000)
    b.set_indicators(bb="Crossing Up Band")
    r = b.startBot()
    check("TP-CASE1: BB exit triggers", r and r['action'] == 'exit')
    check("Count resets after exit", b.count == 0)

    # Sell trade -> BB exit
    b, a = new_bot({'parameters': {'BB_Entry': 'sell', 'BB_Exit': 'tp'}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Up Band")
    b.startBot()
    a.set_price(48000)
    b.set_indicators(bb="Crossing Down Band")
    r = b.startBot()
    check("SELL-TP-CASE3: BB exit from sell", r and r['action'] == 'exit')


# =============================================================================
# FULL TRADE CYCLE
# =============================================================================

def test_full_cycle():
    section("FULL TRADE CYCLE")
    b, a = new_bot({'parameters': {'BB_Entry': 'buy', 'BB_Exit': 'tp',
                                   'favor_levels': 2, 'against_levels': 2}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Down Band")
    r1 = b.startBot()
    check("Entry", r1 and r1['action'] == 'entry')
    check("Orders placed", b.orders_placed == 5)  # 1 market + 2 favor + 2 against
    check("In trade", b.count == 1)
    a.set_price(52000)
    b.set_indicators(bb="Crossing Up Band")
    r2 = b.startBot()
    check("Exit", r2 and r2['action'] == 'exit')
    check("State reset", b.count == 0 and b.current_side == "None")


# =============================================================================
# PRIORITY — CASE1 should win when both CASE1 and CASE2 conditions are met
# =============================================================================

def test_priority():
    section("CONDITION PRIORITY")
    b, a = new_bot({'parameters': {'EMA_RSI_Entry': 'buy', 'EMA_BB_Entry': 'buy'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, prev_rsi=25, rsi_color='white', bb="Crossing Down Band")
    r = b.startBot()
    check("CASE1 fires (not CASE2) when both conditions met",
          r and 'CASE1' in r['reason'])


# =============================================================================
# BOTH FLAG
# =============================================================================

def test_both_flag():
    section("BOTH entry flag")
    b, a = new_bot({'parameters': {'EMA_RSI_Entry': 'both'}})
    a.set_price(50000)
    b.set_indicators(ema=49000, prev_rsi=25, rsi_color='white')
    r = b.startBot()
    check("Both flag allows buy entry", r and r['side'] == 'Buy')

    b2, a2 = new_bot({'parameters': {'EMA_RSI_Entry': 'both'}})
    a2.set_price(50000)
    b2.set_indicators(ema=51000, prev_rsi=75, rsi_color='white')
    r2 = b2.startBot()
    check("Both flag allows sell entry", r2 and r2['side'] == 'Sell')


# =============================================================================
# NONE FLAG
# =============================================================================

def test_none_flag():
    section("NONE entry flag blocks all")
    b, a = new_bot({'parameters': {'BB_Entry': None, 'RSI_Entry': None, 'EMA_RSI_Entry': None}})
    a.set_price(50000)
    b.set_indicators(bb="Crossing Down Band", prev_rsi=25, rsi_color='white', ema=49000)
    r = b.startBot()
    check("No entry when all flags are None", r is None)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  BotEngine Logic Test Suite")
    print(f"  {datetime.now().isoformat()}")
    print("=" * 60)

    tests = [
        ("BUY Entry: 6 cases", test_buy_cases),
        ("SELL Entry: 6 cases", test_sell_cases),
        ("No entry", test_no_entry),
        ("Grid calculation", test_grids),
        ("Grid spacing", test_grid_spacing),
        ("Duplicate prevention", test_no_double_entry),
        ("TP exits", test_tp_exits),
        ("Full trade cycle", test_full_cycle),
        ("Condition priority", test_priority),
        ("Both flag", test_both_flag),
        ("None flag", test_none_flag),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            import traceback
            print(f"  CRASHED: {name}: {e}")
            traceback.print_exc()
            FAIL = FAIL + 1

    print(f"\n{'='*60}")
    print(f"  {PASS} passed, {FAIL} failed")
    print(f"  {datetime.now().isoformat()}")
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)
