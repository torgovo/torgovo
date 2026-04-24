"""
Bot Engine - Trading Execution Engine

Ported from oldbybit.py BybitBots class.
(old)This engine preserves the EXACT same logic, flow, and values from the original
implementation but embeds it into the new adapter/strategy architecture.

Key methods ported 1:1 from oldbybit.py:
- calculated_grid_orders() -> _execute_grid_entry()
- monitor_grid_orders()    -> _monitor_grid_orders()  (the core order-ID based loop)
- monitor_lossProfit()     -> _monitor_loss_profit()
- close_open_order()       -> _close_open_position()
- close_all_orders()       -> _close_all_orders()
- create_order()           -> _create_order() (dollar/coin branching)
- prepare_order_data()     -> _prepare_order_data()

(new)Uses the raw CCXT exchange object directly — same as the original code.
All CCXT calls (create_order, fetch_open_orders, fetch_order, etc.) are
identical to oldbybit.py. The only difference is how the exchange is
initialized (via the adapter pattern instead of hardcoded credentials).

CCXT methods used directly:
- self.exchange.create_order()
- self.exchange.create_market_buy_order_with_cost()
- self.exchange.create_market_sell_order_with_cost()
- self.exchange.fetch_open_orders()
- self.exchange.fetch_order()
- self.exchange.fetch_ticker()
- self.exchange.fetch_positions()
- self.exchange.fetch_position()
- self.exchange.cancel_all_orders()
- self.exchange.amount_to_precision()
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

import pytz
from django.db import close_old_connections

from .execution import BotExecutor

logger = logging.getLogger('trading.engines')


class BotEngine:
    """
    Trading Bot Engine — direct port of oldbybit.py BybitBots.

    Uses raw CCXT exchange instance for all trading operations,
    exactly as the original code did. The adapter is only used
    to initialize the exchange object.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize engine with a plain config dict.
        """
        self.config = config
        self.bot_name = config.get('bot_name', 'unnamed')

        # Build executor (gives us the adapter with initialized CCXT exchange)
        self.executor = BotExecutor.from_config(config)

        # The raw CCXT exchange object — same as oldbybit.py self.exchange
        self.exchange = self.executor.adapter.exchange

        # Symbol formatting (matches oldbybit.py exactly)
        # oldbybit.py: self.symbol = f"{pair_config['pair_symbol']}:{quote_currency}"
        pair_symbol = config.get('symbol', '')
        quote_currency = pair_symbol.split('/')[1] if '/' in pair_symbol else 'USDT'
        self.symbol = f"{pair_symbol}:{quote_currency}"

        # The pair_config dict (matches oldbybit.py self.pair_config)
        self.pair_config = config.get('parameters', {})
        self.pair_config['pair_symbol'] = pair_symbol

        # Indicator state (mirrors oldbybit.py exactly)
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

        self.bot_running = False
        self.monitoring_threads = []
        self.lock = threading.Lock()
        self.monitoring = False
        self._stop_event = threading.Event()

        self.reason = ""
        self.PrevReason = ""
        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0
        self.last_trade_pnl = 0.0
        self.favor_lvl = []
        self.against_lvl = []

        # Condition flags (initialized same as oldbybit.py __init__)
        self.EmaBuyCondition = True if (self.current_price >= self.EMA != 0) else False
        self.EmaSellCondition = True if (self.current_price <= self.EMA != 0) else False
        self.RsiBuyCondition = (self.PrevRSI <= self.pair_config.get('RSI_Lower', 30) and self.RSI_color == 'white')
        self.RsiSellCondition = (self.PrevRSI >= self.pair_config.get('RSI_Upper', 70) and self.RSI_color == 'white')
        self.BBBuyCondition = (self.BB == "Crossing Down Band" or self.BB == "Closed Below Lower Band" or self.BB == "Up Arrow")
        self.BBSellCondition = (self.BB == "Crossing Up Band" or self.BB == "Closed Above Upper Band" or self.BB == "Down Arrow")
        self.NoTrade = True if (self.count == 0 and self.current_side == "None") else False
        self.BuyTrade = True if (self.count == 1 and self.current_side == "Buy") else False
        self.SellTrade = True if (self.count == 1 and self.current_side == "Sell") else False

        # Performance metrics
        self.signals_generated = 0
        self.orders_executed = 0

        logger.info(f"✅ BotEngine initialized for {self.bot_name}")

    # =========================================================================
    # UPDATE CONDITIONS (from oldbybit.py update_conditions — exact copy)
    # =========================================================================

    def update_conditions(self):
        with self.lock:
            logger.info("updating conditions inside Lock")

            self.current_price = self.exchange.fetch_ticker(self.symbol)['last']
            self.EmaBuyCondition = (self.current_price >= self.EMA != 0)
            self.EmaSellCondition = (self.current_price <= self.EMA != 0)

            self.RsiBuyCondition = (self.PrevRSI <= self.pair_config.get('RSI_Lower', 30) and self.RSI_color == 'white')
            self.RsiSellCondition = (self.PrevRSI >= self.pair_config.get('RSI_Upper', 70) and self.RSI_color == 'white')

            self.BBBuyCondition = (
                self.BB == "Crossing Down Band" or self.BB == "Closed Below Lower Band" or self.BB == "Up Arrow")
            self.BBSellCondition = (
                self.BB == "Crossing Up Band" or self.BB == "Closed Above Upper Band" or self.BB == "Down Arrow")

            self.NoTrade = (self.count == 0 and self.current_side == "None")
            self.BuyTrade = (self.count == 1 and self.current_side == "Buy")
            self.SellTrade = (self.count == 1 and self.current_side == "Sell")

    # =========================================================================
    # INDICATOR DATA STRING (from oldbybit.py — exact copy)
    # =========================================================================

    def get_indicator_data(self):
        return (
            f"Symbol: {self.symbol} - CurrentPrice: {self.current_price} - "
            f"EMA: {self.EMA} - BB: {self.BB} - RSI: {self.RSI} - "
            f"PrevRSI: {self.PrevRSI} - RSI_Color: {self.RSI_color} - "
            f"PrevRSI_Color: {self.RSI_prev_color}"
        )

    # =========================================================================
    # RESET STATE (from oldbybit.py reset_trading_state — exact copy)
    # =========================================================================

    def reset_trading_state(self):
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
        self.BB = ""
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
        logger.info(f"Stopping bot for {self.symbol}")
        self.monitoring = False
        self._stop_event.set()
        self._wait_for_threads()
        self.bot_running = False
        logger.info(f"Bot stopped for {self.symbol}")

    # =========================================================================
    # MAIN EXECUTION: startBot() from oldbybit.py — exact copy of logic
    # =========================================================================

    def startBot(self):
        self.update_conditions()
        self.current_price = self.exchange.fetch_ticker(self.symbol)["last"]
        self.bot_running = True

        logger.info(f"current side: {self.current_side}")
        logger.info(f"{self.bot_name} BOT START")

        current_price = self.current_price
        logger.info(f"Current price: {current_price}")

        if self.NoTrade:
            # ---------------------------------------- BUY ----------------------------------------

            # Buy Condition CASE 1 EMA + RSI
            if (self.EmaBuyCondition and self.RsiBuyCondition and
                    (self.pair_config.get('EMA_RSI_Entry') == 'buy' or self.pair_config.get('EMA_RSI_Entry') == 'both')):
                data = self.prepare_order_data("Buy", current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Buy"
                self.reason = 'EMA + RSI BUY LONG (CASE1)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'EMA + RSI BUY LONG (CASE1)', detail)

            # BUY Condition CASE 2 (BB+EMA)
            elif self.BBBuyCondition and self.EmaBuyCondition and (
                    self.pair_config.get('EMA_BB_Entry') == 'buy' or self.pair_config.get('EMA_BB_Entry') == 'both'):
                data = self.prepare_order_data("Buy", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Buy"
                self.reason = 'EMA + BOLLINGER BANDS BUY LONG (CASE2)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'EMA + BOLLINGER BANDS BUY LONG (CASE2)', detail)

            # BUY Condition CASE 3 (BB+RSI)
            elif self.RsiBuyCondition and self.BBBuyCondition and (
                    self.pair_config.get('BB_RSI_Entry') == 'buy' or self.pair_config.get('BB_RSI_Entry') == 'both'):
                data = self.prepare_order_data("Buy", current_price)
                logger.info(f"data of the grid: {data}")
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'BOLLINGER BANDS + RSI BUY LONG (CASE3)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'BOLLINGER BANDS + RSI BUY LONG (CASE3)', detail)

            # BUY Condition CASE 4 (only RSI)
            elif self.RsiBuyCondition and (
                    self.pair_config.get('RSI_Entry') == 'both' or self.pair_config.get('RSI_Entry') == 'buy'):
                data = self.prepare_order_data("Buy", current_price)
                logger.info(f"data of the grid: {data}")
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'ONLY RSI BUY LONG (CASE4)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'ONLY RSI BUY LONG (CASE4)', detail)

            # BUY Condition CASE 5 (ONLY BB)
            elif self.BBBuyCondition and (
                    self.pair_config.get('BB_Entry') == 'buy' or self.pair_config.get('BB_Entry') == 'both'):
                data = self.prepare_order_data("Buy", current_price)
                logger.info(f"data of the grid: {data}")
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'ONLY BOLLINGER BANDS BUY LONG (CASE5)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'ONLY BOLLINGER BANDS BUY LONG (CASE5)', detail)

            # BUY Condition CASE 6 (EMA RSI BB)
            elif self.EmaBuyCondition and self.RsiBuyCondition and self.BBBuyCondition and (
                    self.pair_config.get('EMA_BB_RSI_Entry') == 'buy' or self.pair_config.get('EMA_BB_RSI_Entry') == 'both'):
                data = self.prepare_order_data("Buy", current_price)
                logger.info(f"data of the grid: {data}")
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'EMA RSI BOLLINGER BANDS LONG (CASE6)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'EMA RSI BOLLINGER BANDS BUY LONG (CASE6)', detail)

            # ---------------------------------------- SELL ----------------------------------------

            # Sell Condition CASE 1 (EMA + RSI)
            elif (self.EmaSellCondition and self.RsiSellCondition and
                    (self.pair_config.get('EMA_RSI_Entry') == 'sell' or self.pair_config.get('EMA_RSI_Entry') == 'both')):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'EMA + RSI SELL SHORT (SELL CASE1)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'EMA + RSI SELL SHORT (SELL CASE1)', detail)

            # Sell Condition CASE 2 (BB + EMA)
            elif self.BBSellCondition and self.EmaSellCondition and (
                    self.pair_config.get('EMA_BB_Entry') == 'sell' or self.pair_config.get('EMA_BB_Entry') == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'EMA + BOLLINGER BANDS SELL SHORT (CASE2)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'EMA + BOLLINGER BANDS SELL SHORT (CASE2)', detail)

            # SELL Condition CASE 3 (BB + RSI)
            elif self.BBSellCondition and self.RsiSellCondition and (
                    self.pair_config.get('BB_RSI_Entry') == 'sell' or self.pair_config.get('BB_RSI_Entry') == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'BOLLINGER BANDS + RSI SELL SHORT (CASE3)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'BOLLINGER BANDS + RSI SELL SHORT (CASE3)', detail)

            # SELL Condition CASE 4 (only RSI)
            elif self.RsiSellCondition and (
                    self.pair_config.get('RSI_Entry') == 'sell' or self.pair_config.get('RSI_Entry') == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'ONLY RSI SELL SHORT (CASE4)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'ONLY RSI SELL SHORT (CASE4)', detail)

            # SELL Condition CASE 5 (ONLY BB)
            elif self.BBSellCondition and (
                    self.pair_config.get('BB_Entry') == 'sell' or self.pair_config.get('BB_Entry') == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'ONLY BOLLINGER BANDS SELL SHORT (SELL CASE5)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'ONLY BOLLINGER BANDS SELL SHORT (SELL CASE5)', detail)

            # SELL Condition CASE 6 (EMA RSI BB)
            elif self.EmaSellCondition and self.RsiSellCondition and self.BBSellCondition and (
                    self.pair_config.get('EMA_BB_RSI_Entry') == 'sell' or self.pair_config.get('EMA_BB_RSI_Entry') == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info(f"data of the grid: {data}")
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'EMA RSI BOLLINGER BANDS SELL SHORT (SELL CASE6)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'EMA RSI BOLLINGER BANDS SELL SHORT (SELL CASE6)', detail)

        # ---------------------------------------- TP BUY ----------------------------------------

        elif self.BuyTrade:
            logger.info('Checking TP Buy Cases')

            # TP Buy Position 1 (Only BB)
            if self.BBSellCondition and (self.pair_config.get('BB_Exit') == 'tp' or self.pair_config.get('BB_Exit') == 'both'):
                detail = self.close_all_orders('BOLLINGER BANDS Only (TP CASE 1)')

            # TP Buy Position 2 (Only RSI)
            elif self.RsiSellCondition and (self.pair_config.get('RSI_Exit') == 'tp' or self.pair_config.get('RSI_Exit') == 'both'):
                detail = self.close_all_orders('RSI Only (TP CASE 2)')

            # TP Buy Position 3 (BB + RSI)
            elif self.RsiSellCondition and self.BBSellCondition and (self.pair_config.get('BB_RSI_Exit') == 'tp' or self.pair_config.get('BB_RSI_Exit') == 'both'):
                detail = self.close_all_orders('TP-BUY BOLLINGER BANDS + RSI -- (TP Buy CASE3)')

            # TP Buy Position 4 EMA + BB
            elif self.BBSellCondition and (self.EmaSellCondition or self.EmaBuyCondition) and (self.pair_config.get('EMA_BB_Exit') == 'tp' or self.pair_config.get('EMA_BB_Exit') == 'both'):
                detail = self.close_all_orders('EMA + Bollinger Bands -- (TP-BUY-CASE 4)')

        # ---------------------------------------- TP SELL ----------------------------------------

        elif self.SellTrade:
            logger.info('Checking TP Sell Cases')

            # TP_SELL1 RSI only
            if self.RsiBuyCondition and (self.pair_config.get('RSI_Exit') == 'tp' or self.pair_config.get('RSI_Exit') == 'both'):
                detail = self.close_all_orders('RSI SELL TP (CASE1)')

            # TP_SELL2 (BB + RSI)
            elif self.BBBuyCondition and self.RsiBuyCondition and (self.pair_config.get('BB_RSI_Exit') == 'tp' or self.pair_config.get('BB_RSI_Exit') == 'both'):
                detail = self.close_all_orders('BOLLINGER BANDS + RSI SELL TP (CASE2)')

            # TP_SELL3 (BB)
            elif self.BBBuyCondition and (self.pair_config.get('BB_Exit') == 'tp' or self.pair_config.get('BB_Exit') == 'both'):
                detail = self.close_all_orders('BB SELL TP (SELL TP CASE 3)')

            # TP_SELL4 (EMA + BB)
            elif self.EmaBuyCondition and self.BBBuyCondition and (self.pair_config.get('EMA_BB_Exit') == 'tp' or self.pair_config.get('EMA_BB_Exit') == 'both'):
                detail = self.close_all_orders('EMA BB TP (SELL TP CASE 4)')

    # Alias for webhook compatibility
    def execute_once(self):
        """Webhook-triggered execution. Calls startBot() and returns result dict."""
        result = {'success': False, 'signal': None, 'error': None}
        try:
            self.startBot()
            result['success'] = True
            result['signal'] = self.reason
        except Exception as e:
            logger.error(f"Execute once error: {e}", exc_info=True)
            result['error'] = str(e)
        return result

    # =========================================================================
    # MANUAL ORDERS (from oldbybit.py buy_order, sell_order, close_custom_order)
    # =========================================================================

    async def buy_order(self):
        from asgiref.sync import sync_to_async
        if self.NoTrade:
            data = self.prepare_order_data("Buy", self.current_price)
            logger.info(f"data of the grid: {data}")
            self.count = 1
            self.current_side = "Buy"
            self.PrevReason = self.reason
            self.reason = 'Custom BUY'
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)('BUY', 'CUSTOM BUY ORDER', details=detail)
            self.update_conditions()
        else:
            logger.info("Already Bought")

    async def sell_order(self):
        from asgiref.sync import sync_to_async
        if self.NoTrade:
            data = self.prepare_order_data("Sell", self.current_price)
            logger.info(f"data of the grid: {data}")
            self.count = 1
            self.current_side = "Sell"
            self.PrevReason = self.reason
            self.reason = 'Custom SELL'
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)('SELL', 'CUSTOM SELL ORDER', details=detail)
            self.update_conditions()
        else:
            logger.info("Already Sold")

    async def close_custom_order(self):
        from asgiref.sync import sync_to_async
        if self.BuyTrade or self.SellTrade:
            detail = await sync_to_async(self.close_all_orders)(description="CUSTOM CLOSE ORDER")
        else:
            logger.info('No Trade in Record')

    # =========================================================================
    # PREPARE ORDER DATA (from oldbybit.py — exact copy)
    # =========================================================================

    def prepare_order_data(self, side, current_price):
        config = self.pair_config
        if self.pair_config.get('Amount_Type') == "dollar":
            quantity_dollar = config['quantity']
            favor_level_qty_dollar = config['favor_level_qty']
            against_level_qty_dollar = config['against_level_qty']

            quantity = round(config['quantity'] / current_price, 4)
            favor_level_qty = round(config['favor_level_qty'] / current_price, 4)
            against_level_qty = round(config['against_level_qty'] / current_price, 4)
            logger.info(f"dollar calculated - coins: {quantity}, {favor_level_qty}, {against_level_qty}")
        else:
            quantity = config['quantity']
            favor_level_qty = config['favor_level_qty']
            against_level_qty = config['against_level_qty']
            quantity_dollar = None
            favor_level_qty_dollar = None
            against_level_qty_dollar = None
            logger.info(f"coin calculated: {quantity}, {favor_level_qty}, {against_level_qty}")

        quantity = float(self.exchange.amount_to_precision(self.symbol, quantity))
        favor_level_qty = float(self.exchange.amount_to_precision(self.symbol, favor_level_qty))
        against_level_qty = float(self.exchange.amount_to_precision(self.symbol, against_level_qty))

        data = {
            "category": 'futures',
            "symbol": self.symbol,
            "Order_Type": config.get('Order_Type', 'market'),
            "side": side,
            "qty": quantity,
            "qty_dollar": quantity_dollar,
            "price": current_price,
            "favor_levels": config.get('favor_levels', 5),
            "against_levels": config.get('against_levels', 5),
            "favor_level_qty": favor_level_qty,
            "against_level_qty": against_level_qty,
            "favor_level_qty_dollar": favor_level_qty_dollar,
            "against_level_qty_dollar": against_level_qty_dollar,
            "favor_level_difference": config.get('favor_level_difference', 0.5),
            "against_level_difference": config.get('against_level_difference', 0.5),
        }
        return data

    # =========================================================================
    # FETCH CURRENT PRICE (from oldbybit.py — exact copy)
    # =========================================================================

    def fetch_current_price(self):
        ticker, symbol = self.exchange.fetch_ticker, self.symbol
        self.current_price = ticker(symbol)["last"]
        thread_id = threading.get_ident()
        logger.info(f"Thread ID: {thread_id} | Fetched current price: {self.current_price}")
        return self.current_price

    # =========================================================================
    # SAVE ORDER (from oldbybit.py — adapted for new models)
    # =========================================================================

    def save_order(self, side, description, details=None):
        """Place an order and save it to the database."""
        try:
            from apps.bots.models import Order, Indicator
            from django.contrib.auth import get_user_model

            user_id = self.config.get('user_id')
            if not user_id:
                logger.warning("No user_id in config, skipping order save")
                return

            User = get_user_model()
            user = User.objects.get(id=user_id)

            indicator = Indicator.objects.create(
                Pair=self.symbol,
                user=user,
                EMA=self.EMA,
                RSI=self.RSI,
                Prev_RSI=self.PrevRSI,
                Color=self.RSI_color or '',
                Prev_Color=self.RSI_prev_color or '',
                BB=self.BB or '',
                TSI=self.TSI,
                ADX=self.ADX,
            )
            order = Order.objects.create(
                Pair=self.symbol,
                user=user,
                Indicators=indicator,
                Side=side,
                Category="futures",
                Order_type="Market",
                Quantity=self.pair_config.get("quantity", 0),
                Price=self.current_price,
                Exchange=self.config.get('exchange_name', 'Bybit'),
                Description=description,
                Details=details if isinstance(details, dict) else {'raw': str(details)},
            )
            logger.info(f"Placed order: {order}")
            self.orders_executed += 1
            return order
        except Exception as e:
            logger.error(f"Failed to save order: {e}")

    # =========================================================================
    # CREATE ORDER (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def create_order(self, order_type, side, quantity, price):
        try:
            if self.pair_config.get('Amount_Type') == "dollar":
                if order_type == 'market':
                    data = self.exchange.create_market_order_with_cost(self.symbol, side, quantity, params={'category': 'linear'})
                elif order_type == 'limit':
                    data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            else:
                data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            logger.info(f"Order type: {order_type} - Side: {side} - Quantity: {quantity} - Price: {price}")
            return data
        except Exception as e:
            logger.error(f"Cannot create order: {e}")

    # =========================================================================
    # CLOSE OPEN ORDER (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def close_open_order(self, description):
        try:
            closing_symbol = self.symbol.replace('/', '')
            position = self.exchange.fetch_positions(symbols=closing_symbol, params={'category': 'linear'})
            size = float(position[0]['contracts'])
            self.Unrealized_Pnl = float(position[0]['unrealizedPnl'])

            side = position[0]['side']
            if self.pair_config.get('SLTP_Type') == 'percentage':
                self.Percentage = self.Unrealized_Pnl / size * 1000
                self.last_trade_pnl = self.Unrealized_Pnl

            if side == 'short':
                try:
                    detail = self.exchange.create_order(symbol=closing_symbol, type='market', amount=size, side='buy', params={'reduceOnly': True})
                    self.save_order(side, description, detail)
                    return detail
                except Exception as e:
                    logger.error(f"Closing short order failed: {e}")

                logger.info('Short Order Closed')

            elif side == 'long':
                try:
                    detail = self.exchange.create_order(symbol=closing_symbol, type='market', amount=size, side='sell', params={'reduceOnly': True})
                    self.save_order(side, description, detail)
                    return detail
                except Exception as e:
                    logger.error(f"Closing long order failed: {e}")

                logger.info('Long Order Closed')

        except Exception as e:
            logger.error(f"No position found: {e}")
            return None

    # =========================================================================
    # CLOSE ALL ORDERS (from oldbybit.py — exact copy)
    # =========================================================================

    def close_all_orders(self, description):
        logger.info(f"cancelling all limit orders of self.symbol: {self.symbol}, pair_config['pair_symbol']: {self.pair_config.get('pair_symbol')}")
        closing_symbol = self.symbol.replace('/', '')
        self.reset_trading_state()
        self.exchange.cancel_all_orders(symbol=closing_symbol)
        position = self.close_open_order(description)
        self.reason = description
        logger.info(f"All Orders Closed: {description}")
        return position

    # =========================================================================
    # CALCULATE GRIDS (from oldbybit.py — exact copy)
    # =========================================================================

    def calculate_grids(self, side):
        favor_levels = []
        against_levels = []
        if side.lower() == 'buy':
            for levels in range(self.pair_config.get("favor_levels", 5)):
                favor_levels.append(
                    round(self.current_price * (1 + (levels + 1) * self.pair_config.get('favor_level_difference', 0.5) / 100), 6))
            for levels in range(self.pair_config.get('against_levels', 5)):
                against_levels.append(
                    round(self.current_price * (1 - (levels + 1) * self.pair_config.get('against_level_difference', 0.5) / 100), 6))

        if side.lower() == 'sell':
            for levels in range(self.pair_config.get('favor_levels', 5)):
                favor_levels.append(
                    round(self.current_price * (1 - (levels + 1) * self.pair_config.get('favor_level_difference', 0.5) / 100), 6))
            for levels in range(self.pair_config.get('against_levels', 5)):
                against_levels.append(
                    round(self.current_price * (1 + (levels + 1) * self.pair_config.get('against_level_difference', 0.5) / 100), 6))

        return favor_levels, against_levels

    # =========================================================================
    # CALCULATED GRID ORDERS (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def calculated_grid_orders(self, data):
        self.bot_running = True
        self.monitoring = True
        logger.info(f"Calculating Grids for {data['symbol']}")

        symbol = data['symbol']
        side = data['side']
        qty = data['qty']
        logger.info(f"quantity: {qty} - type {type(qty)}")
        price = data['price']
        favor_level_qty = data['favor_level_qty']
        against_level_qty = data['against_level_qty']
        logger.info(f"Grid data: {data['symbol']} - {data['Order_Type']} - {side} - {qty} - {price}")

        # Open initial order
        initial_order = None
        try:
            if self.pair_config.get('Amount_Type') == "dollar":
                qty_dollar = data['qty_dollar']
                logger.info(f"pair config amount type dollar {self.pair_config.get('Amount_Type')} - cost in dollars:{qty_dollar} - side: {side}")
                if side == 'Buy':
                    initial_order = self.exchange.create_market_buy_order_with_cost(self.symbol, cost=qty_dollar, params={'category': 'linear'})
                    logger.info(f"initial market buy order with dollar cost: {initial_order}")
                elif side == 'Sell':
                    initial_order = self.exchange.create_market_sell_order_with_cost(self.symbol, cost=qty_dollar, params={'category': 'linear'})
                    logger.info(f"initial market sell order with dollar cost: {initial_order}")

            elif self.pair_config.get('Amount_Type') == "coin":
                logger.info(f"pair config amount type coin - quantity in coins:{qty} - side: {side}")
                initial_order = self.create_order(order_type=self.pair_config.get('Order_Type', 'market'), side=side, quantity=qty, price=price)
            else:
                logger.warning(f"neither dollar nor coin: {self.pair_config.get('Amount_Type')}")
        except Exception as e:
            logger.error(f"Creating initial order failed: {e}")

        favor_levels, against_levels = self.calculate_grids(side)
        # updating levels on global variable for indicator page
        self.favor_lvl, self.against_lvl = favor_levels, against_levels

        if side.lower() == 'buy':
            # Open grid orders
            for level in favor_levels:
                level_price = float(level)
                try:
                    logger.info(f"quantity: {qty} - type {type(qty)}")
                    self.create_order('limit', 'sell', favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating favor order failed: {e}")

            for level in against_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'buy', against_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating against order failed: {e}")

        if side.lower() == 'sell':
            for level in favor_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'buy', favor_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating favor order failed: {e}")

            for level in against_levels:
                level_price = float(level)
                try:
                    self.create_order('limit', 'sell', against_level_qty, level_price)
                except Exception as e:
                    logger.error(f"Creating against order failed: {e}")

        # Start monitoring orders in a separate thread
        time.sleep(3)
        monitoring_thread = threading.Thread(
            target=self.monitor_grid_orders,
            args=(side, price, favor_levels, against_levels, favor_level_qty, against_level_qty),
            name=f"GridMonitor-{self.symbol}-{side}"
        )
        monitoring_thread.daemon = True
        monitoring_thread.start()
        self.monitoring_threads.append(monitoring_thread)

        # Start SL/TP monitoring thread
        sltp_thread = threading.Thread(
            target=self.monitor_lossProfit,
            args=(side,),
            name=f"SLTP-{self.symbol}-{side}"
        )
        sltp_thread.daemon = True
        sltp_thread.start()
        self.monitoring_threads.append(sltp_thread)

        self.signals_generated += 1
        return initial_order

    # =========================================================================
    # MONITOR GRID ORDERS (from oldbybit.py — exact copy, uses raw CCXT)
    # ORDER-ID BASED grid monitoring loop
    # =========================================================================

    def monitor_grid_orders(self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty):
        last_favor_level = None
        last_against_level = None
        logger.info('Monitoring Grid Orders.')
        self.current_price = self.fetch_current_price()
        logger.info(f"{self.symbol} Current price: {self.current_price}  CurrentSide: {side} on KEYPAIR {self.symbol}, owner={self.bot_name}")

        # --- Order-ID maps to track orders by id and price ---
        favor_order_map = {}   # price -> order_id
        against_order_map = {} # price -> order_id

        # Helper to place an order and register mapping
        def place_and_register(price, ord_side, qty, register_map):
            try:
                resp = self.create_order('limit', ord_side, qty, float(price))
                logger.info(f"order response: {resp}")
                order_id = resp.get('id') if isinstance(resp, dict) else getattr(resp, 'id', None)
                if order_id is None:
                    order_id = resp.get('orderId') if isinstance(resp, dict) else None
                if order_id is None:
                    # fallback: find the order by price in open orders
                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                    logger.info('fetched open orders')
                    for o in open_orders:
                        if float(o.get('price', 0)) == float(price) and o.get('side', '').lower() == ord_side.lower():
                            order_id = o.get('id') or o.get('orderId') or o.get('clientOrderId')
                            break
                if order_id:
                    register_map[float(price)] = order_id
                else:
                    logger.warning(f"Placed order but no id found for price {price} side {ord_side}.")
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

        # Seed levels with current open order prices if not already
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
                close_old_connections()

                # fetch open orders once per iteration
                open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')

                # function to check if an order id is filled (order-based)
                def is_filled(order_id):
                    if not order_id:
                        return False
                    try:
                        o = self.exchange.fetch_order(order_id, symbol=self.symbol, params={'category': 'linear'})
                        logger.info(f"fetch order in is_filled function: {o}")
                        status = o.get('status') or o.get('state')
                        if isinstance(status, str) and status.lower() in ('closed', 'filled', 'filled_partially'):
                            return True
                        return False
                    except Exception:
                        try:
                            for o2 in open_orders:
                                if (o2.get('id') == order_id) or (o2.get('orderId') == order_id) or (o2.get('clientOrderId') == order_id):
                                    return False
                            return True
                        except:
                            return False

                # --- Process favor orders ---
                favor_keys = sorted(list(favor_order_map.keys()), reverse=reverse_for_favor)
                for price in favor_keys:
                    order_id = favor_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Favor order filled at {executed_level} id={order_id}")
                        favor_order_map.pop(price, None)
                        try:
                            if price in [float(x) for x in favor_levels]:
                                for i, v in enumerate(favor_levels):
                                    if float(v) == price:
                                        favor_levels.pop(i)
                                        break
                        except Exception:
                            pass

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
                                logger.info(f"{'Buy @' if side.lower() == 'buy' else 'Sell @'} {place_price}")
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
                                logger.info(f"{'Buy @' if side.lower() == 'buy' else 'Sell @'} {place_price}")
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

                # --- Process against orders ---
                against_keys = sorted(list(against_order_map.keys()), reverse=reverse_for_against)
                for price in against_keys:
                    order_id = against_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Against order filled at {executed_level} id={order_id}")
                        against_order_map.pop(price, None)
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
                                logger.info(f"{'Sell @' if side.lower() == 'buy' else 'Buy @'} {place_price}")
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
                                logger.info(f"{'Sell @' if side.lower() == 'buy' else 'Buy @'} {place_price}")
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

                # small sleep to avoid rate limits
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error in monitor_grid_orders: {e}")
                time.sleep(2)

    # =========================================================================
    # MONITOR LOSS/PROFIT (from oldbybit.py — exact copy)
    # =========================================================================

    def monitor_lossProfit(self, side):
        loss_profit_percentage = 0.0
        time.sleep(4)

        while self.monitoring and not self._stop_event.is_set():
            try:
                loss_profit_percentage = self.check_lossProfit_percent()
                if loss_profit_percentage is None:
                    loss_profit_percentage = 0.0

                elif self.pair_config.get('SL_Exit') == 'sl' or self.pair_config.get('SL_Exit') == 'both':
                    if loss_profit_percentage <= self.pair_config.get('Stop_Loss', -999):
                        logger.info(f"SL HIT! Value: {loss_profit_percentage}")
                        self.close_all_orders('SL hit Position and closed')

                if self.pair_config.get('SL_Exit') == 'tp' or self.pair_config.get('SL_Exit') == 'both':
                    if loss_profit_percentage >= self.pair_config.get('Take_Profit', 999):
                        logger.info(f"TP HIT! Value: {loss_profit_percentage}")
                        self.close_all_orders('TP hit Position and closed')

            except Exception as e:
                logger.error(f"Loss Profit Exception: {str(e)}")

            if self._stop_event.wait(timeout=5.0):
                break

    # =========================================================================
    # CHECK LOSS/PROFIT PERCENT (from oldbybit.py — exact copy, uses raw CCXT)
    # =========================================================================

    def check_lossProfit_percent(self):
        try:
            position = self.exchange.fetch_position(symbol=self.symbol, params={'category': 'linear'})
            if position:
                size = float(position['notional'])
                pnl = float(position['unrealizedPnl'])
                self.Unrealized_Pnl = pnl
                self.Percentage = pnl / size * 1000
            else:
                logger.info(f"No position found on {self.symbol} of bot: {self.bot_name}")
        except Exception as e:
            logger.error(f"Check Loss Profit Exception: {str(e)}")
            self.Unrealized_Pnl = 0.0
            self.Percentage = 0.0

        logger.info(f"Pair: {self.symbol}  Percentage: {self.Percentage}  PNL: {self.Unrealized_Pnl}  Price: {self.current_price}")

        if self.pair_config.get('SLTP_Type') == 'percentage':
            return self.Percentage
        elif self.pair_config.get('SLTP_Type') == 'dollars':
            return self.Unrealized_Pnl

    # =========================================================================
    # QTY HELPER (from oldbybit.py — exact copy)
    # =========================================================================

    def qty(self):
        if self.pair_config.get('Amount_Type') == "dollar":
            quantity = round(self.pair_config['quantity'] / self.current_price, 4)
            favor_level_qty = round(self.pair_config['favor_level_qty'] / self.current_price, 4)
            against_level_qty = round(self.pair_config['against_level_qty'] / self.current_price, 4)
            logger.info(f"dollar calculated: {quantity}, {favor_level_qty}, {against_level_qty}")
            return quantity, favor_level_qty, against_level_qty
        else:
            quantity = self.pair_config['quantity']
            favor_level_qty = self.pair_config['favor_level_qty']
            against_level_qty = self.pair_config['against_level_qty']
            logger.info(f"coin calculated: {quantity}, {favor_level_qty}, {against_level_qty}")
            return quantity, favor_level_qty, against_level_qty

    # =========================================================================
    # STATUS & METRICS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        return {
            'bot_name': self.bot_name,
            'symbol': self.symbol,
            'exchange': self.config.get('exchange_name', ''),
            'is_running': self.monitoring,
            'bot_running': self.bot_running,
            'current_side': self.current_side,
            'current_price': self.current_price,
            'count': self.count,
            'reason': self.reason,
            'percentage_pnl': self.Percentage,
            'unrealized_pnl': self.Unrealized_Pnl,
            'signals_generated': self.signals_generated,
            'orders_executed': self.orders_executed,
            'favor_levels': list(self.favor_lvl),
            'against_levels': list(self.against_lvl),
            'indicators': {
                'EMA': self.EMA,
                'RSI': self.RSI,
                'PrevRSI': self.PrevRSI,
                'BB': self.BB,
                'RSI_color': self.RSI_color,
            },
        }

    def __str__(self) -> str:
        return f"BotEngine({self.bot_name})"

    def __repr__(self) -> str:
        return f"BotEngine(name={self.bot_name}, symbol={self.symbol})"