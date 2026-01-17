"""
Quantum AI Trading Strategy
Exchange-AGNOSTIC trading logic - works with any exchange adapter
Contains all trading logic from oldbybit.py
"""
import logging
import threading
import time
import pytz
from datetime import datetime
from typing import Dict, Any, List, Optional

from apps.bots.models import Order, Indicator, PairConfig
from apps.exchanges.models import ExchangeCredentials
from trading.adapters import BaseExchangeAdapter, get_exchange_adapter

logger = logging.getLogger('trading.strategies.quantum_ai')


class QuantumAIStrategy:
    """
    Quantum AI Trading Strategy
    
    This is the main trading logic - SAME for all exchanges.
    Uses an exchange adapter to handle exchange-specific API calls.
    
    Features:
    - Grid trading with favor/against levels
    - Order monitoring and replacement
    - SL/TP management
    - Indicator-based entry/exit conditions
    """
    
    def __init__(self, user, pair_config: PairConfig, exchange_credentials: ExchangeCredentials):
        """
        Initialize Quantum AI Strategy.
        
        Args:
            user: Django User instance
            pair_config: PairConfig model instance
            exchange_credentials: ExchangeCredentials model instance
        """
        self.user = user
        self.pair_config_model = pair_config
        self.pair_config = self._load_pair_config(pair_config)
        self.symbol = pair_config.pair_symbol
        
        # Initialize exchange adapter
        creds = exchange_credentials.get_decrypted_credentials()
        demo_mode = getattr(user, 'Demo', False)
        self.exchange = get_exchange_adapter(
            exchange_credentials.exchange_name,
            creds,
            demo_mode
        )
        
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
        
        # Update conditions
        self.update_conditions()
        
        logger.info(f"QuantumAI Strategy initialized for {self.symbol} on {self.exchange.exchange_name}")
    
    def _load_pair_config(self, pair_config: PairConfig) -> dict:
        """Convert PairConfig model to dictionary."""
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
            'RSI_Lower': getattr(pair_config, 'RSI_Lower', 30),
            'RSI_Upper': getattr(pair_config, 'RSI_Upper', 70),
        }
    
    # ==================== STATE MANAGEMENT ====================
    
    def reset_trading_state(self):
        """Reset all trading state variables."""
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
        """Wait for all monitoring threads to finish."""
        for thread in self.monitoring_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
                if thread.is_alive():
                    logger.warning(f"Thread {thread.name} did not stop gracefully")
        self.monitoring_threads.clear()
    
    def stop_bot(self):
        """Stop the bot and clean up."""
        logger.info(f"Stopping bot for {self.symbol}")
        self.monitoring = False
        self._stop_event.set()
        self._wait_for_threads()
        self.bot_running = False
        logger.info(f"Bot stopped for {self.symbol}")
    
    def update_conditions(self):
        """Update trading conditions based on indicators."""
        with self.lock:
            self.current_price = self.exchange.get_current_price(self.symbol)
            
            self.EmaBuyCondition = (self.current_price >= self.EMA != 0)
            self.EmaSellCondition = (self.current_price <= self.EMA != 0)
            
            self.RsiBuyCondition = (self.PrevRSI <= self.pair_config['RSI_Lower'] and self.RSI_color == 'white')
            self.RsiSellCondition = (self.PrevRSI >= self.pair_config['RSI_Upper'] and self.RSI_color == 'white')
            
            self.BBBuyCondition = self.BB in ["Crossing Down Band", "Closed Below Lower Band", "Up Arrow"]
            self.BBSellCondition = self.BB in ["Crossing Up Band", "Closed Above Upper Band", "Down Arrow"]
            
            self.NoTrade = (self.count == 0 and self.current_side == "None")
            self.BuyTrade = (self.count == 1 and self.current_side == "Buy")
            self.SellTrade = (self.count == 1 and self.current_side == "Sell")
    
    # ==================== GRID CALCULATION ====================
    
    def calculate_grids(self, side: str) -> tuple:
        """
        Calculate grid levels based on current price.
        
        Args:
            side: 'buy' or 'sell'
            
        Returns:
            (favor_levels, against_levels) lists
        """
        favor_levels = []
        against_levels = []
        
        if side.lower() == 'buy':
            # Buy: favor above (sell orders), against below (buy orders)
            for i in range(self.pair_config["favor_levels"]):
                favor_levels.append(
                    round(self.current_price * (1 + (i + 1) * self.pair_config['favor_level_difference'] / 100), 6)
                )
            for i in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 - (i + 1) * self.pair_config['against_level_difference'] / 100), 6)
                )
        else:
            # Sell: favor below (buy orders), against above (sell orders)
            for i in range(self.pair_config['favor_levels']):
                favor_levels.append(
                    round(self.current_price * (1 - (i + 1) * self.pair_config['favor_level_difference'] / 100), 6)
                )
            for i in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 + (i + 1) * self.pair_config['against_level_difference'] / 100), 6)
                )
        
        return favor_levels, against_levels
    
    def prepare_order_data(self, side: str, current_price: float) -> dict:
        """Prepare order data with quantity calculations."""
        config = self.pair_config
        
        if config['Amount_Type'] == "dollar":
            quantity_dollar = config['quantity']
            favor_qty_dollar = config['favor_level_qty']
            against_qty_dollar = config['against_level_qty']
            
            quantity = round(config['quantity'] / current_price, 4)
            favor_level_qty = round(config['favor_level_qty'] / current_price, 4)
            against_level_qty = round(config['against_level_qty'] / current_price, 4)
        else:
            quantity = config['quantity']
            favor_level_qty = config['favor_level_qty']
            against_level_qty = config['against_level_qty']
            quantity_dollar = None
            favor_qty_dollar = None
            against_qty_dollar = None
        
        # Format to exchange precision
        quantity = self.exchange.amount_to_precision(self.symbol, quantity)
        favor_level_qty = self.exchange.amount_to_precision(self.symbol, favor_level_qty)
        against_level_qty = self.exchange.amount_to_precision(self.symbol, against_level_qty)
        
        return {
            "symbol": self.symbol,
            "side": side,
            "qty": quantity,
            "qty_dollar": quantity_dollar,
            "price": current_price,
            "favor_level_qty": favor_level_qty,
            "against_level_qty": against_level_qty,
            "favor_qty_dollar": favor_qty_dollar,
            "against_qty_dollar": against_qty_dollar,
        }
    
    # ==================== GRID TRADING ====================
    
    def start_grid_trading(self, side: str) -> Dict[str, Any]:
        """
        Start grid trading.
        
        Args:
            side: 'Buy' or 'Sell'
            
        Returns:
            Initial order response
        """
        self.update_conditions()
        self.bot_running = True
        self.monitoring = True
        self.current_side = side
        self.count = 1
        
        data = self.prepare_order_data(side, self.current_price)
        logger.info(f"Starting grid trading: {side} on {self.symbol}")
        
        # Place initial order
        initial_order = None
        try:
            amount_in_dollars = self.pair_config['Amount_Type'] == "dollar"
            amount = data['qty_dollar'] if amount_in_dollars else data['qty']
            
            initial_order = self.exchange.create_market_order(
                self.symbol,
                side.lower(),
                amount,
                amount_in_dollars=amount_in_dollars
            )
            logger.info(f"Initial order placed: {initial_order}")
        except Exception as e:
            logger.error(f"Failed to place initial order: {e}")
        
        # Calculate and place grid orders
        favor_levels, against_levels = self.calculate_grids(side)
        self.favor_lvl = favor_levels
        self.against_lvl = against_levels
        
        if side.lower() == 'buy':
            # Place sell orders at favor levels (above)
            for level in favor_levels:
                try:
                    self.exchange.create_limit_order(self.symbol, 'sell', data['favor_level_qty'], level)
                except Exception as e:
                    logger.error(f"Failed to place favor order at {level}: {e}")
            
            # Place buy orders at against levels (below)
            for level in against_levels:
                try:
                    self.exchange.create_limit_order(self.symbol, 'buy', data['against_level_qty'], level)
                except Exception as e:
                    logger.error(f"Failed to place against order at {level}: {e}")
        else:
            # Sell side: opposite
            for level in favor_levels:
                try:
                    self.exchange.create_limit_order(self.symbol, 'buy', data['favor_level_qty'], level)
                except Exception as e:
                    logger.error(f"Failed to place favor order at {level}: {e}")
            
            for level in against_levels:
                try:
                    self.exchange.create_limit_order(self.symbol, 'sell', data['against_level_qty'], level)
                except Exception as e:
                    logger.error(f"Failed to place against order at {level}: {e}")
        
        # Start monitoring thread
        time.sleep(3)
        monitoring_thread = threading.Thread(
            target=self.monitor_grid_orders,
            args=(side, self.current_price, favor_levels, against_levels, 
                  data['favor_level_qty'], data['against_level_qty']),
            name=f"GridMonitor-{self.symbol}-{side}"
        )
        monitoring_thread.daemon = True
        monitoring_thread.start()
        self.monitoring_threads.append(monitoring_thread)
        
        # Save order to database
        self.save_order(side, f"Grid {side} started on {self.exchange.exchange_name}", initial_order)
        
        return initial_order
    
    # ==================== GRID MONITORING (FROM OLDBYBIT.PY) ====================
    
    def monitor_grid_orders(self, side, entry_price, favor_levels, against_levels, 
                           favor_level_qty, against_level_qty):
        """
        Monitor grid orders and replace filled orders.
        LOGIC PRESERVED FROM oldbybit.py lines 803-1061
        """
        last_favor_level = None
        last_against_level = None
        logger.info(f"Monitoring grid orders for {self.symbol}")
        
        # Order ID tracking maps
        favor_order_map = {}
        against_order_map = {}
        
        def place_and_register(price, ord_side, qty, register_map):
            """Place order and register in map."""
            try:
                resp = self.exchange.create_limit_order(self.symbol, ord_side, qty, float(price))
                order_id = self.exchange.get_order_id(resp)
                if order_id:
                    register_map[float(price)] = order_id
                return order_id
            except Exception as e:
                logger.error(f"Error placing order at {price}: {e}")
                return None
        
        # Initialize maps with current open orders
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            for o in open_orders:
                try:
                    p = round(float(o.get('price')), 8)
                    s = o.get('side', '').lower()
                    oid = self.exchange.get_order_id(o)
                    
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
                except:
                    continue
        except Exception as e:
            logger.warning(f"Could not seed open orders: {e}")
        
        # Seed levels
        for p in favor_order_map.keys():
            if p not in favor_levels:
                favor_levels.append(p)
        for p in against_order_map.keys():
            if p not in against_levels:
                against_levels.append(p)
        
        reverse_for_favor = (side.lower() == 'sell')
        reverse_for_against = (side.lower() == 'buy')
        favor_levels.sort(reverse=reverse_for_favor)
        against_levels.sort(reverse=reverse_for_against)
        
        # Main monitoring loop
        while self.monitoring:
            try:
                open_orders = self.exchange.fetch_open_orders(self.symbol)
                current_buy_prices = set(float(o['price']) for o in open_orders if o['side'].lower() == 'buy')
                current_sell_prices = set(float(o['price']) for o in open_orders if o['side'].lower() == 'sell')
                
                def is_filled(order_id):
                    if not order_id:
                        return False
                    try:
                        o = self.exchange.fetch_order(order_id, self.symbol)
                        return self.exchange.is_order_filled(o)
                    except:
                        for o2 in open_orders:
                            if self.exchange.get_order_id(o2) == order_id:
                                return False
                        return True
                
                # Process favor orders
                favor_keys = sorted(list(favor_order_map.keys()), reverse=reverse_for_favor)
                for price in favor_keys:
                    order_id = favor_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Favor order filled at {executed_level}")
                        favor_order_map.pop(price, None)
                        
                        # Remove from levels
                        favor_levels = [l for l in favor_levels if float(l) != price]
                        
                        # Place opposite order
                        if entry_price not in favor_levels and entry_price not in against_levels:
                            place_price = float(entry_price)
                            ord_side = 'buy' if side.lower() == 'buy' else 'sell'
                            
                            if ord_side == 'buy' and place_price in current_buy_prices:
                                continue
                            if ord_side == 'sell' and place_price in current_sell_prices:
                                continue
                            
                            new_oid = place_and_register(place_price, ord_side, against_level_qty, against_order_map)
                            logger.info(f"Placed against order: {ord_side} @ {place_price}")
                            
                            if new_oid:
                                against_levels.append(place_price)
                                against_levels.sort(reverse=reverse_for_against)
                                self.against_lvl = against_levels[:]
                        
                        last_favor_level = executed_level
                        entry_price = executed_level
                        self.favor_lvl = favor_levels[:]
                
                # Process against orders
                against_keys = sorted(list(against_order_map.keys()), reverse=reverse_for_against)
                for price in against_keys:
                    order_id = against_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Against order filled at {executed_level}")
                        against_order_map.pop(price, None)
                        
                        against_levels = [l for l in against_levels if float(l) != price]
                        
                        if entry_price not in favor_levels and entry_price not in against_levels:
                            place_price = float(entry_price)
                            ord_side = 'sell' if side.lower() == 'buy' else 'buy'
                            
                            if ord_side == 'buy' and place_price in current_buy_prices:
                                continue
                            if ord_side == 'sell' and place_price in current_sell_prices:
                                continue
                            
                            new_oid = place_and_register(place_price, ord_side, favor_level_qty, favor_order_map)
                            logger.info(f"Placed favor order: {ord_side} @ {place_price}")
                            
                            if new_oid:
                                favor_levels.append(place_price)
                                favor_levels.sort(reverse=reverse_for_favor)
                                self.favor_lvl = favor_levels[:]
                        
                        last_against_level = executed_level
                        entry_price = executed_level
                        self.against_lvl = against_levels[:]
                
                time.sleep(1)
            
            except Exception as e:
                logger.error(f"Error in monitor_grid_orders: {e}")
                time.sleep(2)
    
    # ==================== POSITION MANAGEMENT ====================
    
    def close_all_orders(self, description: str) -> Optional[Dict[str, Any]]:
        """Cancel all orders and close position."""
        logger.info(f"Closing all orders: {description}")
        
        self.reset_trading_state()
        self.exchange.cancel_all_orders(self.symbol)
        
        # Close position
        pnl_info = self.exchange.get_position_pnl(self.symbol)
        if pnl_info['size'] > 0:
            try:
                result = self.exchange.close_position(
                    self.symbol,
                    pnl_info['side'],
                    pnl_info['size']
                )
                self.save_order(pnl_info['side'], description, result)
                return result
            except Exception as e:
                logger.error(f"Failed to close position: {e}")
        
        self.reason = description
        return None
    
    # ==================== DATABASE ====================
    
    def save_order(self, side: str, description: str, details: Any):
        """Save order to database."""
        try:
            indicator = Indicator.objects.create(
                Pair=self.symbol,
                user=self.user,
                EMA=self.EMA,
                RSI=self.RSI,
                Prev_RSI=self.PrevRSI,
                Color=self.RSI_color or "",
                Prev_Color=self.RSI_prev_color or "",
                BB=str(self.BB) if self.BB else "",
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
                Exchange=self.exchange.exchange_name.capitalize(),
                Description=description,
                Details=str(details) if details else ""
            )
            logger.info(f"Order saved: {order.id}")
            return order
        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return None
    
    def get_indicator_data(self) -> str:
        """Get formatted indicator data."""
        return (f"Symbol: {self.symbol} - Price: {self.current_price} - "
                f"EMA: {self.EMA} - RSI: {self.RSI} - BB: {self.BB}")
