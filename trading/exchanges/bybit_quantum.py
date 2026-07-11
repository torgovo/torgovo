"""
Bybit Quantum AI Bot Implementation
Adapted from proven old project code with grid trading, order monitoring, and SL/TP
"""
import logging
import threading
import time
import ccxt
import pytz
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone

from apps.bots.models import Order, Indicator, PairConfig
from apps.exchanges.models import ExchangeCredentials
from .base import BaseExchangeBot

logger = logging.getLogger('trading.bybit')


class BybitQuantumBot(BaseExchangeBot):
    """
    Bybit Quantum AI Bot with proven grid trading logic
    Preserves the original BybitBots implementation from old project
    """
    
    def __init__(self, user, pair_config: PairConfig, exchange_credentials: ExchangeCredentials):
        """
        Initialize Bybit Quantum Bot
        
        Args:
            user: Django User instance
            pair_config: PairConfig model instance
            exchange_credentials: ExchangeCredentials model instance
        """
        super().__init__(user, pair_config.pair_symbol, exchange_credentials)
        
        self.user = user
        self.pair_config_model = pair_config
        self.pair_config = self._load_pair_config(pair_config)
        
        # Symbol formatting for Bybit futures
        quote_currency = self.pair_config['pair_symbol'].split('/')[1]
        self.symbol = f"{self.pair_config['pair_symbol']}:{quote_currency}"
        
        # Technical indicators
        self.EMA = 0.0
        self.BB = None
        self.TSI = None
        self.ADX = None
        self.RSI = 0.0
        self.PrevRSI = 0.0
        self.RSI_color = None
        self.RSI_prev_color = None
        
        # Trading state
        self.current_side = "None"
        self.count = 0
        self.current_price = 0.0
        
        # Bot control
        self.bot_running = False
        self.monitoring_threads = []
        self.lock = threading.Lock()
        self.monitoring = False
        self._stop_event = threading.Event()
        
        # Trade tracking
        self.reason = ""
        self.PrevReason = ""
        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0
        self.last_trade_pnl = 0.0
        self.favor_lvl = []
        self.against_lvl = []
        
        # Initialize exchange
        self.exchange = self._initialize_bybit_exchange()
        
        # Update conditions
        self.update_conditions()
    
    def _load_pair_config(self, pair_config: PairConfig) -> dict:
        """Convert PairConfig model to dictionary for compatibility"""
        return {
            'id': str(pair_config.id),
            'pair_symbol': pair_config.pair_symbol,
            'quantity': float(pair_config.favor_level_qty) if pair_config.favor_level_qty else 0.0,
            'favor_levels': pair_config.favor_levels,
            'against_levels': pair_config.against_levels,
            'favor_level_qty': float(pair_config.favor_level_qty) if pair_config.favor_level_qty else 0.0,
            'against_level_qty': float(pair_config.against_level_qty) if pair_config.against_level_qty else 0.0,
            'favor_level_difference': float(pair_config.favor_level_difference) if pair_config.favor_level_difference else 1.0,
            'against_level_difference': float(pair_config.against_level_difference) if pair_config.against_level_difference else 1.0,
            'Amount_Type': pair_config.Amount_Type,
            'Order_Type': pair_config.Order_Type,
            'Stop_Loss': float(pair_config.Stop_Loss) if pair_config.Stop_Loss else 0.0,
            'Take_Profit': float(pair_config.Take_Profit) if pair_config.Take_Profit else 0.0,
            'SLTP_Type': pair_config.SLTP_Type,
            # Entry/Exit conditions
            'EMA_RSI_Entry': pair_config.EMA_RSI_Entry if hasattr(pair_config, 'EMA_RSI_Entry') else 'both',
            'EMA_BB_Entry': pair_config.EMA_BB_Entry if hasattr(pair_config, 'EMA_BB_Entry') else 'both',
            'BB_RSI_Entry': pair_config.BB_RSI_Entry if hasattr(pair_config, 'BB_RSI_Entry') else 'both',
            'RSI_Entry': pair_config.RSI_Entry if hasattr(pair_config, 'RSI_Entry') else 'both',
            'BB_Entry': pair_config.BB_Entry if hasattr(pair_config, 'BB_Entry') else 'both',
            'EMA_BB_RSI_Entry': pair_config.EMA_BB_RSI_Entry if hasattr(pair_config, 'EMA_BB_RSI_Entry') else 'both',
            'BB_Exit': pair_config.BB_Exit if hasattr(pair_config, 'BB_Exit') else 'both',
            'RSI_Exit': pair_config.RSI_Exit if hasattr(pair_config, 'RSI_Exit') else 'both',
            'BB_RSI_Exit': pair_config.BB_RSI_Exit if hasattr(pair_config, 'BB_RSI_Exit') else 'both',
            'EMA_BB_Exit': pair_config.EMA_BB_Exit if hasattr(pair_config, 'EMA_BB_Exit') else 'both',
            'SL_Exit': pair_config.SL_Exit if hasattr(pair_config, 'SL_Exit') else 'both',
            'RSI_Lower': pair_config.RSI_Lower if hasattr(pair_config, 'RSI_Lower') else 30,
            'RSI_Upper': pair_config.RSI_Upper if hasattr(pair_config, 'RSI_Upper') else 70,
        }
    
    def _initialize_bybit_exchange(self):
        """Initialize CCXT Bybit exchange with user credentials"""
        try:
            # Get decrypted credentials
            creds = self.credentials.get_decrypted_credentials()
            
            exchange = ccxt.bybit({
                "apiKey": creds['api_key'],
                "secret": creds['secret_key'],
                "enableRateLimit": True,
                "options": {
                    "defaultType": "linear",  # USDT perpetual futures
                    "trade.type": "linear",
                }
            })
            
            # Enable demo trading if configured
            if hasattr(self.user, 'Demo') and self.user.Demo:
                exchange.enable_demo_trading(True)
            
            logger.info(f"Bybit exchange initialized for {self.user.username}")
            return exchange
        except Exception as e:
            logger.error(f"Bybit exchange initialization failed: {e}")
            raise
    
    def reset_trading_state(self):
        """Reset all trading state variables"""
        self.monitoring = False
        self._stop_event.set()
        
        self.EMA = 0.0
        self.BB = None
        self.TSI = None
        self.ADX = None
        self.RSI = 0.0
        self.PrevRSI = 0.0
        self.RSI_color = None
        self.RSI_prev_color = None
        self.current_side = "None"
        self.count = 0
        self.PrevReason = self.reason
        self.reason = ""
        self.bot_running = False
        
        self.favor_lvl = []
        self.against_lvl = []
        self.update_conditions()
        
        self._wait_for_threads()
    
    def _wait_for_threads(self):
        """Wait for all monitoring threads to finish"""
        for thread in self.monitoring_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
                if thread.is_alive():
                    logger.warning(f"Thread {thread.name} did not stop gracefully")
        self.monitoring_threads.clear()
    
    def stop_bot(self):
        """Properly stop the bot and clean up all threads"""
        logger.info(f"Stopping Bybit bot for {self.symbol}")
        self.monitoring = False
        self._stop_event.set()
        self._wait_for_threads()
        self.bot_running = False
        logger.info(f"Bybit bot stopped for {self.symbol}")
    
    def update_conditions(self):
        """Update all trading conditions based on current indicators"""
        with self.lock:
            logger.info("Updating conditions inside Lock")
            
            self.current_price = self.exchange.fetch_ticker(self.symbol)['last']
            self.EmaBuyCondition = (self.current_price >= self.EMA != 0)
            self.EmaSellCondition = (self.current_price <= self.EMA != 0)
            
            self.RsiBuyCondition = (self.PrevRSI <= self.pair_config['RSI_Lower'] and self.RSI_color == 'white')
            self.RsiSellCondition = (self.PrevRSI >= self.pair_config['RSI_Upper'] and self.RSI_color == 'white')
            
            self.BBBuyCondition = (
                self.BB == "Crossing Down Band" or self.BB == "Closed Below Lower Band" or self.BB == "Up Arrow")
            self.BBSellCondition = (
                self.BB == "Crossing Up Band" or self.BB == "Closed Above Upper Band" or self.BB == "Down Arrow")
            
            self.NoTrade = (self.count == 0 and self.current_side == "None")
            self.BuyTrade = (self.count == 1 and self.current_side == "Buy")
            self.SellTrade = (self.count == 1 and self.current_side == "Sell")
    
    def get_indicator_data(self):
        """Get formatted indicator data string"""
        return f'Symbol: {self.symbol} - CurrentPrice: {self.current_price} - EMA: {self.EMA} - BB: {self.BB} - RSI: {self.RSI} - PrevRSI: {self.PrevRSI} - RSI_Color: {self.RSI_color} - PrevRSI_Color: {self.RSI_prev_color}'
    
    def fetch_current_price(self):
        """Fetch the current market price"""
        ticker = self.exchange.fetch_ticker(self.symbol)
        self.current_price = ticker["last"]
        thread_id = threading.get_ident()
        logger.info(f"Thread ID: {thread_id} | Fetched current price: {self.current_price}")
        return self.current_price
    
    def save_order(self, side, description, details):
        """Save order to database"""
        indicator = Indicator.objects.create(
            Pair=self.symbol,
            user=self.user,
            EMA=self.EMA,
            RSI=self.RSI,
            Prev_RSI=self.PrevRSI,
            Color=self.RSI_color,
            Prev_Color=self.RSI_prev_color,
            BB=self.BB if self.BB else "",
            TSI=self.TSI if self.TSI else 0.0,
            ADX=self.ADX if self.ADX else 0.0
        )
        
        order = Order.objects.create(
            Pair=self.symbol,
            user=self.user,
            PairConfig=self.pair_config_model,
            Indicators=indicator,
            Side=side,
            Category="futures",
            Order_type="Market",
            Quantity=self.pair_config["quantity"],
            Price=self.current_price,
            Exchange="Bybit",
            Description=description,
            Details=details
        )
        logger.info(f"Saved order: {order}")
        return order
    
    def calculate_grids(self, side):
        """Calculate grid levels based on current price and configuration"""
        favor_levels = []
        against_levels = []
        
        if side.lower() == 'buy':
            # Buy side: favor levels above (sell orders), against levels below (buy orders)
            for level in range(self.pair_config["favor_levels"]):
                favor_levels.append(
                    round(self.current_price * (1 + (level + 1) * self.pair_config['favor_level_difference'] / 100), 6))
            for level in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 - (level + 1) * self.pair_config['against_level_difference'] / 100), 6))
        
        elif side.lower() == 'sell':
            # Sell side: favor levels below (buy orders), against levels above (sell orders)
            for level in range(self.pair_config['favor_levels']):
                favor_levels.append(
                    round(self.current_price * (1 - (level + 1) * self.pair_config['favor_level_difference'] / 100), 6))
            for level in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 + (level + 1) * self.pair_config['against_level_difference'] / 100), 6))
        
        return favor_levels, against_levels
    
    def create_order(self, order_type, side, quantity, price):
        """Create order on Bybit exchange"""
        try:
            if self.pair_config['Amount_Type'] == "dollar":
                if order_type == 'market':
                    data = self.exchange.create_market_order_with_cost(
                        self.symbol, side, quantity, params={'category': 'linear'})
                elif order_type == 'limit':
                    data = self.exchange.create_order(
                        self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            else:
                # Coin type
                data = self.exchange.create_order(
                    self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            
            logger.info(f'Order created: type={order_type}, side={side}, qty={quantity}, price={price}')
            return data
        except Exception as e:
            logger.error(f"Cannot create order: {e}")
            raise
    
    def prepare_order_data(self, side, current_price):
        """Prepare order data with proper quantity calculations"""
        config = self.pair_config
        
        if config['Amount_Type'] == "dollar":
            # Keep dollar values for market orders
            quantity_dollar = config['quantity']
            favor_level_qty_dollar = config['favor_level_qty']
            against_level_qty_dollar = config['against_level_qty']
            
            # Convert to coins for limit orders
            quantity = round(config['quantity'] / current_price, 4)
            favor_level_qty = round(config['favor_level_qty'] / current_price, 4)
            against_level_qty = round(config['against_level_qty'] / current_price, 4)
        else:
            # Coin type
            quantity = config['quantity']
            favor_level_qty = config['favor_level_qty']
            against_level_qty = config['against_level_qty']
            quantity_dollar = None
            favor_level_qty_dollar = None
            against_level_qty_dollar = None
        
        # Precision formatting
        quantity = float(self.exchange.amount_to_precision(self.symbol, quantity))
        favor_level_qty = float(self.exchange.amount_to_precision(self.symbol, favor_level_qty))
        against_level_qty = float(self.exchange.amount_to_precision(self.symbol, against_level_qty))
        
        data = {
            "category": 'futures',
            "symbol": self.symbol,
            "Order_Type": config['Order_Type'],
            "side": side,
            "qty": quantity,
            "qty_dollar": quantity_dollar,
            "price": current_price,
            "favor_levels": config['favor_levels'],
            "against_levels": config['against_levels'],
            "favor_level_qty": favor_level_qty,
            "against_level_qty": against_level_qty,
            "favor_level_qty_dollar": favor_level_qty_dollar,
            "against_level_qty_dollar": against_level_qty_dollar,
            "favor_level_difference": config['favor_level_difference'],
            "against_level_difference": config['against_level_difference']
        }
        return data

    def calculated_grid_orders(self, data):
        """
        Calculate and place grid orders
        PRESERVES ORIGINAL LOGIC FROM OLD PROJECT
        """
        self.bot_running = True
        self.monitoring = True
        logger.info(f'Bybit Calculating Grids for {data["symbol"]}')
        
        symbol = data['symbol']
        side = data['side']
        qty = data['qty']
        price = data['price']
        favor_level_qty = data['favor_level_qty']
        against_level_qty = data['against_level_qty']
        
        # Open initial order
        initial_order = None
        try:
            if self.pair_config['Amount_Type'] == "dollar":
                qty_dollar = data['qty_dollar']
                if side == 'Buy':
                    initial_order = self.exchange.create_market_buy_order_with_cost(
                        self.symbol, cost=qty_dollar, params={'category': 'linear'})
                elif side == 'Sell':
                    initial_order = self.exchange.create_market_sell_order_with_cost(
                        self.symbol, cost=qty_dollar, params={'category': 'linear'})
            else:
                initial_order = self.create_order(
                    order_type=self.pair_config['Order_Type'], side=side, quantity=qty, price=price)
        except Exception as e:
            logger.error(f'Creating initial order failed: {e}')
        
        favor_levels, against_levels = self.calculate_grids(side)
        self.favor_lvl, self.against_lvl = favor_levels, against_levels
        
        # Place grid orders
        if side.lower() == 'buy':
            for level in favor_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'sell', favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f'Creating favor order failed: {e}')
            
            for level in against_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'buy', against_level_qty, level_price)
                except Exception as e:
                    logger.error(f'Creating against order failed: {e}')
        
        elif side.lower() == 'sell':
            for level in favor_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'buy', favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f'Creating favor order failed: {e}')
            
            for level in against_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'sell', against_level_qty, level_price)
                except Exception as e:
                    logger.error(f'Creating against order failed: {e}')
        
        # Start monitoring thread
        time.sleep(3)
        monitoring_thread = threading.Thread(
            target=self.monitor_grid_orders,
            args=(side, price, favor_levels, against_levels, favor_level_qty, against_level_qty),
            name=f"GridMonitor-{self.symbol}-{side}"
        )
        monitoring_thread.daemon = True
        monitoring_thread.start()
        self.monitoring_threads.append(monitoring_thread)
        
        return initial_order
    
    # NOTE: The monitor_grid_orders method is very long (400+ lines)
    # It should be continued in a separate file or split into smaller methods
    # For now, I'll add a placeholder that references the original implementation
    
    def monitor_grid_orders(self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty):
        """
        Monitor grid orders and replace filled orders
        PRESERVES EXACT LOGIC FROM OLD PROJECT (oldbybit.py lines 803-1061)
        
        This method continuously monitors open orders and when an order fills:
        - Creates opposite order at entry price
        - Updates grid levels
        - Tracks last filled level
        """
        last_favor_level = None
        last_against_level = None
        logger.info('Monitoring Bybit Grid Orders.')
        self.current_price = self.fetch_current_price()
        logger.info(f"Bybit {self.symbol} Current price: {self.current_price} CurrentSide: {side} on KEYPAIR {self.symbol}, owner={self.user.username}")
        
        # --- Maps to track orders by id and price ---
        favor_order_map = {}  # price -> order_id for favor side orders
        against_order_map = {}  # price -> order_id for against side orders
        
        # Helper to place an order and register mapping
        def place_and_register(price, ord_side, qty, register_map):
            try:
                resp = self.create_order('limit', ord_side, qty, float(price))
                logger.info(f"order response: {resp}\n")
                order_id = resp.get('id') if isinstance(resp, dict) else getattr(resp, 'id', None)
                if order_id is None:
                    order_id = resp.get('orderId') if isinstance(resp, dict) else None
                if order_id is None:
                    # Fallback: find order by price in open orders
                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                    logger.info(f'fetched open orders for id lookup\n')
                    for o in open_orders:
                        if float(o.get('price', 0)) == float(price) and o.get('side', '').lower() == ord_side.lower():
                            order_id = o.get('id') or o.get('orderId') or o.get('clientOrderId')
                            break
                if order_id:
                    register_map[float(price)] = order_id
                else:
                    logger.warning(f'Placed order but no id found for price {price} side {ord_side}.')
                return order_id
            except Exception as e:
                logger.error(f"Error placing order at {price} side {ord_side}: {e}")
                return None
        
        # --- INITIALIZE maps with currently-open grid orders ---
        try:
            open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
            for o in open_orders:
                try:
                    p = round(float(o.get('price')), 8)
                except:
                    continue
                s = o.get('side', '').lower()
                oid = o.get('id') or o.get('orderId') or o.get('clientOrderId')
                if s == 'sell':
                    if side.lower() == 'buy':
                        favor_order_map[p] = oid
                    else:
                        against_order_map[p] = oid
                elif s == 'buy':
                    if side.lower() == 'buy':
                        against_order_map[p] = oid
                    else:
                        favor_order_map[p] = oid
        except Exception as e:
            logger.warning(f"Could not seed open orders into maps: {e}")
        
        # Seed levels with current open order prices
        for p in favor_order_map.keys():
            if p not in favor_levels:
                favor_levels.append(p)
        for p in against_order_map.keys():
            if p not in against_levels:
                against_levels.append(p)
        
        # Sort appropriately based on side
        reverse_for_favor = (side.lower() == 'sell')
        reverse_for_against = (side.lower() == 'buy')
        favor_levels.sort(reverse=reverse_for_favor)
        against_levels.sort(reverse=reverse_for_against)
        
        # --- MAIN monitor loop (order-id based) ---
        while self.monitoring:
            try:
                # Fetch open orders once per iteration
                open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                
                # Function to check if an order id is filled
                def is_filled(order_id):
                    if not order_id:
                        return False
                    try:
                        o = self.exchange.fetch_order(order_id, symbol=self.symbol, params={'category': 'linear'})
                        logger.info(f'fetch order in "is_filled" function {o}')
                        status = o.get('status') or o.get('state')
                        if isinstance(status, str) and status.lower() in ('closed', 'filled', 'filled_partially'):
                            return True
                        return False
                    except Exception:
                        # Fallback: if not in open orders, assume filled
                        try:
                            for o2 in open_orders:
                                if (o2.get('id') == order_id) or (o2.get('orderId') == order_id) or (o2.get('clientOrderId') == order_id):
                                    return False
                            return True
                        except Exception:
                            return False
                
                # --- Process favor orders (when filled, create against orders) ---
                favor_keys = sorted(list(favor_order_map.keys()), reverse=reverse_for_favor)
                for price in favor_keys:
                    order_id = favor_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Favor order filled at {executed_level} id={order_id}")
                        favor_order_map.pop(price, None)
                        
                        # Remove from favor_levels
                        try:
                            if price in [float(x) for x in favor_levels]:
                                for i, v in enumerate(favor_levels):
                                    if float(v) == price:
                                        favor_levels.pop(i)
                                        break
                        except Exception:
                            pass
                        
                        # Create opposite order logic
                        if last_favor_level is not None and executed_level >= float(last_favor_level):
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                place_price = float(entry_price)
                                ord_side = 'buy' if side.lower() == 'buy' else 'sell'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, against_level_qty, against_order_map)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - {"Buy" if side.lower() == "buy" else "Sell"} @ {place_price}')
                                if new_oid:
                                    against_levels.append(place_price)
                                    against_levels.sort(reverse=reverse_for_against)
                                    self.against_lvl = against_levels[:]
                                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                                    current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                                    current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                            last_favor_level = executed_level
                            entry_price = executed_level
                        else:
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                place_price = float(entry_price)
                                ord_side = 'buy' if side.lower() == 'buy' else 'sell'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, against_level_qty, against_order_map)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - {"Buy" if side.lower() == "buy" else "Sell"} @ {place_price}')
                                if new_oid:
                                    against_levels.append(place_price)
                                    against_levels.sort(reverse=reverse_for_against)
                                    self.against_lvl = against_levels[:]
                                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                                    current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                                    current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                            last_favor_level = executed_level
                            entry_price = executed_level
                        favor_levels.sort(reverse=reverse_for_favor)
                        self.favor_lvl = favor_levels[:]
                
                # --- Process against orders (when filled, create favor orders) ---
                against_keys = sorted(list(against_order_map.keys()), reverse=reverse_for_against)
                for price in against_keys:
                    order_id = against_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"{datetime.now(pytz.timezone('Asia/Karachi'))} Against order filled at {executed_level} id={order_id}")
                        against_order_map.pop(price, None)
                        
                        # Remove from against_levels
                        try:
                            if price in [float(x) for x in against_levels]:
                                for i, v in enumerate(against_levels):
                                    if float(v) == price:
                                        against_levels.pop(i)
                                        break
                        except Exception:
                            pass
                        
                        if last_against_level is not None and executed_level <= float(last_against_level):
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                place_price = float(entry_price)
                                ord_side = 'sell' if side.lower() == 'buy' else 'buy'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, favor_level_qty, favor_order_map)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - {"Sell" if side.lower() == "buy" else "Buy"} @ {place_price}')
                                if new_oid:
                                    favor_levels.append(place_price)
                                    favor_levels.sort(reverse=reverse_for_favor)
                                    self.favor_lvl = favor_levels[:]
                                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                                    current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                                    current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                            last_against_level = executed_level
                            entry_price = executed_level
                        else:
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                place_price = float(entry_price)
                                ord_side = 'sell' if side.lower() == 'buy' else 'buy'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, favor_level_qty, favor_order_map)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - {"Sell" if side.lower() == "buy" else "Buy"} @ {place_price}')
                                if new_oid:
                                    favor_levels.append(place_price)
                                    favor_levels.sort(reverse=reverse_for_favor)
                                    self.favor_lvl = favor_levels[:]
                                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                                    current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                                    current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                            last_against_level = executed_level
                            entry_price = executed_level
                        against_levels.sort(reverse=reverse_for_against)
                        self.against_lvl = against_levels[:]
                
                # Sleep to avoid rate limits
                time.sleep(1)
            
            except Exception as e:
                logger.error(f'Error in monitor_grid_orders: {e}')
                time.sleep(2)
    
    def close_open_order(self, description):
        """Close open position"""
        try:
            closing_symbol = self.symbol.replace('/', '')
            position = self.exchange.fetch_positions(symbols=closing_symbol, params={'category': 'linear'})
            
            size = float(position[0]['contracts'])
            self.Unrealized_Pnl = float((position[0]['unrealizedPnl']))
            side = position[0]['side']
            
            if self.pair_config['SLTP_Type'] == 'percentage':
                self.Percentage = self.Unrealized_Pnl / size * 1000
                self.last_trade_pnl = self.Unrealized_Pnl
            
            if side == 'short':
                detail = self.exchange.create_order(
                    symbol=closing_symbol, type='market', amount=size, side='buy', params={'reduceOnly': True})
                self.save_order(side, description, detail)
                return detail
            elif side == 'long':
                detail = self.exchange.create_order(
                    symbol=closing_symbol, type='market', amount=size, side='sell', params={'reduceOnly': True})
                self.save_order(side, description, detail)
                return detail
        except Exception as e:
            logger.error(f"No position found: {e}")
            return None
    
    def close_all_orders(self, description):
        """Cancel all orders and close position"""
        logger.info(f"Closing all orders: {description}")
        closing_symbol = self.symbol.replace('/', '')
        self.reset_trading_state()
        self.exchange.cancel_all_orders(symbol=closing_symbol)
        position = self.close_open_order(description)
        self.reason = description
        logger.info(f'All Bybit orders closed: {description}')
        return position
