import logging
import threading
import time
import ccxt
import pytz
import json
from datetime import datetime

import requests
from asgiref.sync import sync_to_async

from bot.models import Order, Indicator

# Create a logger
logger = logging.getLogger('Torgovo.BybitBot')



class BybitBots:
    def __init__(self, user, pair_config):
        self.user = user
        self.pair_config = pair_config
        quote_currency = self.pair_config['pair_symbol'].split('/')[1]  # Gets 'USDT'
        self.symbol = f"{pair_config['pair_symbol']}:{quote_currency}"
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
        self.current_price = 0.0
        self.exchange = self._initialize_exchange()

        self.bot_running = False
        self.monitoring_threads = []
        self.lock = threading.Lock()
        self.monitoring = False
        self._stop_event = threading.Event()

        # self.symbol = pair_config['pair_symbol']
        self.reason = ""
        self.PrevReason = ""
        self.Percentage = 0.0
        self.Unrealized_Pnl = 0.0
        self.last_trade_pnl = 0.0
        self.favor_lvl = []
        self.against_lvl = []

        # self.is_master = False
        # self.trading_bot_model = None
        # self.bot_follower = None
        # self.wallet_percentage = 100.0  # Default full wallet
        # self.original_pair_config = pair_config.copy()

        self.EmaBuyCondition = True if (self.current_price >= self.EMA != 0) else False
        self.EmaSellCondition = True if (self.current_price <= self.EMA != 0) else False

        self.RsiBuyCondition = (self.PrevRSI <= pair_config['RSI_Lower'] and self.RSI_color == 'white')
        self.RsiSellCondition = (self.PrevRSI >= pair_config['RSI_Upper'] and self.RSI_color == 'white')

        self.BBBuyCondition = (
                self.BB == "Crossing Down Band" or self.BB == "Closed Below Lower Band" or self.BB == "Up Arrow")
        self.BBSellCondition = (
                self.BB == "Crossing Up Band" or self.BB == "Closed Above Upper Band" or self.BB == "Down Arrow")

        self.NoTrade = True if (self.count == 0 and self.current_side == "None") else False
        self.BuyTrade = True if (self.count == 1 and self.current_side == "Buy") else False
        self.SellTrade = True if (self.count == 1 and self.current_side == "Sell") else False

    def _initialize_exchange(self):

        # setting = User.objects.filter(user=self.user).first()
        try:
            self.exchange = ccxt.bybit({
                "apiKey": self.user.API,
                "secret": self.user.SECRET,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "linear",
                    "trade.type": "linear", # for USDT perpetual futures

                }
            })
            if self.user.Demo:
                self.exchange.enable_demo_trading(True)

            print("Bybit exchange initialized")
            logger.info("Bybit exchange initialized")
            return self.exchange
        except Exception as e:
            print('Bybit Exchange initialized failed', e)
            logger.info('Bybit Exchange initialized failed', e)

    def reset_trading_state(self):
        self.monitoring = False
        self._stop_event.set()  # Signal all threads to stop
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
        
        # Wait for all threads to finish
        self._wait_for_threads()

    def _wait_for_threads(self):
        """Wait for all monitoring threads to finish"""
        for thread in self.monitoring_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)  # Wait up to 5 seconds
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

    def update_conditions(self):
        with self.lock:
            print("updating conditions inside Lock")
            logger.info("updating conditions inside Lock")

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
        indicator_data = f'Symbol: {self.symbol} - CurrentPrice: {self.current_price} - EMA: {self.EMA} - BB: {self.BB} - RSI: {self.RSI} - PrevRSI: {self.PrevRSI} - RSI_Color: {self.RSI_color} - PrevRSI_Color: {self.RSI_prev_color}'
        return indicator_data

    def startBot(self):
        self.update_conditions()
        self.current_price = self.exchange.fetch_ticker(self.symbol)["last"]
        self.bot_running = True

        print("current side: ", self.current_side)
        print(f"{self.user.username} BYBIT BOT START")

        logger.info(f"current side:  {self.current_side}")
        logger.info(f"{self.user.username} BYBIT BOT START")

        current_price = self.current_price
        print(current_price)
        logger.info(current_price)

        # while self.bot_running:
            # print("Running Routine")

        if self.NoTrade:
            # print('checking conditions')
# -------------------------------------------- BUY ------------------------------------------------

            # Buy Condition CASE 1 EMA+ RSI
            if (self.EmaBuyCondition and self.RsiBuyCondition and
                    (self.pair_config['EMA_RSI_Entry'] == 'buy' or self.pair_config['EMA_RSI_Entry'] == 'both')):

                data = self.prepare_order_data("Buy", current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Buy"
                self.reason = 'EMA + RSI BUY LONG (CASE1)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit EMA + RSI BUY LONG (CASE1)', detail)
                self.print_details("BUY1", detail)

            # BUY Condition CASE 2 (BB+EMA)
            elif self.BBBuyCondition and self.EmaBuyCondition and (
                    self.pair_config['EMA_BB_Entry'] == 'buy' or self.pair_config['EMA_BB_Entry'] == 'both'):
                data = self.prepare_order_data("Buy", self.current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Buy"
                self.reason ='Bybit EMA + BOLLINGER BANDS BUY LONG (CASE2)) '
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit EMA + BOLLINGER BANDS BUY LONG (CASE2)) ', detail)
                self.print_details("BUY2", details=detail)

            # BUY Condition CASE 3 (BB+RSI)
            elif self.RsiBuyCondition and self.BBBuyCondition and (
                    self.pair_config['BB_RSI_Entry'] == 'buy' or self.pair_config['BB_RSI_Entry'] == 'both'):

                data = self.prepare_order_data("Buy", current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'Bybit BOLLINGER BANDS + RSI BUY LONG (CASE3)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit BOLLINGER BANDS + RSI BUY LONG (CASE3)', detail)
                self.print_details("BUY3", detail)

            # BUY Condition CASE 4 (only RSI)
            elif self.RsiBuyCondition and (
                    self.pair_config['RSI_Entry'] == 'both' or self.pair_config['RSI_Entry'] == 'buy'):
                data = self.prepare_order_data("Buy", current_price)
                print('data of the grid', data)
                logger.info(f'data of the grid: {data}')
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'Bybit ONLY RSI BUY LONG (CASE4)'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit ONLY RSI BUY LONG (CASE4)', detail)
                self.print_details("BUY4", detail)

                # BUY Condition CASE 5 (ONLY BB)
            elif self.BBBuyCondition and (
                    self.pair_config['BB_Entry'] == 'buy' or self.pair_config['BB_Entry'] == 'both'):
                data = self.prepare_order_data("Buy", current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'Bybit ONLY BOLLINGER BANDS  BUY LONG (CASE5))'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit ONLY BOLLINGER BANDS  BUY LONG (CASE5))', detail)
                self.print_details("BUY5", detail)

            # BUY Condition CASE 6 (EMA RSI BB)
            elif self.EmaBuyCondition and self.RsiBuyCondition and self.BBBuyCondition and (self.pair_config['EMA_BB_RSI_Entry'] == 'buy' or self.pair_config['EMA_BB_RSI_Entry'] == 'both'):
                data = self.prepare_order_data("Buy", current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.current_side = "Buy"
                self.count = 1
                self.reason = 'Bybit EMA RSI BOLLINGER BANDS  LONG (CASE6))'
                detail = self.calculated_grid_orders(data)
                self.save_order('BUY', 'Bybit EMA RSI BOLLINGER BANDS  BUY LONG (CASE6))', detail)
                self.print_details("BUY6", detail)

# -------------------------------------------- SELL------------------------------------------------

            # Sell Condition CASE 1 (EMA + RSI)
            elif (self.EmaSellCondition and self.RsiSellCondition and
                    (self.pair_config['EMA_RSI_Entry'] == 'buy' or self.pair_config['EMA_RSI_Entry'] == 'both')):
                data = self.prepare_order_data("Sell", self.current_price)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'Bybit EMA + RSI SELL SHORT  (SELL CASE1)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit EMA + RSI SELL SHORT  (SELL CASE1)', details=detail)
                self.print_details("SELL1", detail)

            # Sell Condition CASE 2 (BB + EMA)
            elif self.BBSellCondition and self.EmaSellCondition and (
                    self.pair_config['EMA_BB_Entry'] == 'sell' or self.pair_config['EMA_BB_Entry'] == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'Bybit EMA + BOLLINGER BANDS SELL SHORT  (CASE2)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit EMA + BOLLINGER BANDS SELL SHORT  (CASE2)', details=detail)
                self.print_details("SELL2", detail)


            # SEll Condition CASE 3 (BB +RSI)
            elif self.BBSellCondition and self.RsiSellCondition and (
                    self.pair_config['BB_RSI_Entry'] == 'sell' or self.pair_config['BB_RSI_Entry'] == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Sell"
                self.reason ='Bybit BOLLINGER BANDS + RSI SELL SHORT (CASE3)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit BOLLINGER BANDS + RSI SELL SHORT (CASE3)', details=detail)
                self.print_details("SELL3", detail)


            # SELL Condition CASE 4 (only RSI)
            elif self.RsiSellCondition and (
                    self.pair_config['RSI_Entry'] == 'sell' or self.pair_config['RSI_Entry'] == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                print('data of the grid', data)
                logger.info('data of the grid', data)
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'Bybit ONLY RSI SELL SHORT  (CASE4)'
                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit ONLY RSI SELL SHORT  (CASE4)', details=detail)
                self.print_details("SELL4", detail)

            # SELL Condition CASE 5 (ONLY BB)
            elif self.BBSellCondition and (
                    self.pair_config['BB_Entry'] == 'sell' or self.pair_config['BB_Entry'] == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'Bybit ONLY BOLLINGER BANDS SELL SHORT  (SELL CASE5)'
                print('data of the grid', data)
                logger.info('data of the grid', data)

                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit ONLY BOLLINGER BANDS SELL SHORT  (SELL CASE5)', details=detail)
                self.print_details("SELL5", detail)

            # SELL Condition CASE 6 (EMA RSI BB)
            elif self.EmaSellCondition and self.RsiSellCondition and self.BBSellCondition and (self.pair_config['EMA_BB_RSI_Entry'] == 'sell' or self.pair_config['EMA_BB_RSI_Entry'] == 'both'):
                data = self.prepare_order_data("Sell", self.current_price)
                self.count = 1
                self.current_side = "Sell"
                self.reason = 'Bybit EMA RSI BOLLINGER BANDS SELL SHORT  (SELL CASE6)'
                print('data of the grid', data)
                logger.info('data of the grid', data)

                detail = self.calculated_grid_orders(data)
                self.save_order('SELL', 'Bybit EMA RSI BOLLINGER BANDS SELL SHORT  (SELL CASE6)', details=detail)
                self.print_details("SELL6", detail)




# ------------------------------------------------TP BUY ---------------------------------------------------------------

        elif self.BuyTrade:
            # TP Buy Position 1 (Only BB)
            print('Checking TP Buy Cases\n')
            logger.info('Checking TP Buy Cases\n')
            if self.BBSellCondition and (self.pair_config['BB_Exit'] == 'tp' or self.pair_config['BB_Exit'] == 'both'):
                # if (BB == "Closed Above Upper Band" or BB == "Down Arrow") and PrevRSI >= config.RSI_Upper and RSI_color == "white" and RSI_prev_color == "red" and count == 1 and current_side == "Buy" and config.TP_BUY1:
                detail = self.close_all_orders('Bybit BOLLINGER BANDS Only (TP CASE 1))')
                self.print_details("TP_BUY1", detail)



            # TP Buy Position 2 (Only RSI
            elif self.RsiSellCondition and (self.pair_config['RSI_Exit'] == 'tp' or self.pair_config['RSI_Exit'] == 'both'):
                detail= self.close_all_orders('Bybit RSI Only (TP CASE 2)')
                self.print_details("TP_BUY2", detail)


            # TP Buy Position 3 (BB + RSI)
            elif self.RsiSellCondition and self.BBSellCondition and (self.pair_config['BB_RSI_Exit'] == 'tp' or self.pair_config['BB_RSI_Exit'] == 'both'):

                detail = self.close_all_orders("Bybit TP-BUY BOLLINGER BANDS + RSI -- (TP Buy CASE3)")
                self.print_details("TP_BUY3", detail)

            # TP Buy Position 4 EMA + BB
            elif self.BBSellCondition and (self.EmaSellCondition or self.EmaBuyCondition) and (self.pair_config['EMA_BB_Exit'] == 'tp' or self.pair_config['EMA_BB_Exit'] == 'both'):
                detail = self.close_all_orders("Bybit EMA + Bollinger Bands -- (TP-BUY-CASE 4)")
                self.print_details("TP_BUY4", detail)

            # SL Buy Position

# -------------------------------------------------------------------- TP Sell position   -------------------------------------
        elif self.SellTrade:
            # TP_SELL1 RSI only
            #  when the candle closes Below Lower BB | green triangle | when better RSI 1 will be Below 30 and turns white from red
            if self.RsiBuyCondition and (self.pair_config['RSI_Exit'] == 'tp' or self.pair_config['RSI_Exit'] == 'both'):
                detail = self.close_all_orders('Bybit RSI  SELL TP (CASE1)', )
                self.print_details("TP_SELL1", detail)

            # TP_SELL2 (BB + RSI)
            elif self.BBBuyCondition and self.RsiBuyCondition and (self.pair_config['BB_RSI_Exit'] == 'tp' or self.pair_config['BB_RSI_Exit'] == 'both'):
                detail = self.close_all_orders('Bybit BOLLINGER BANDS + RSI SELL TP (CASE2)')
                self.print_details("TP_SELL2", detail)


            # TP_SELL3 (BB)
            elif self.BBBuyCondition and (self.pair_config['BB_Exit'] == 'tp' or self.pair_config['BB_Exit'] == 'both'):
                detail = self.close_all_orders('Bybit BB SELl TP  (SELL TP CASE 3)')
                self.print_details("TP_SELL3", detail)

            # TP_SELL4 ( EMA + BB)
            elif self.EmaBuyCondition and self.BBBuyCondition and (self.pair_config['EMA_BB_Exit'] == 'tp' or self.pair_config['EMA_BB_Exit'] == 'both'):
                detail = self.close_all_orders("Bybit EMA BB TP  (SELL TP CASE 4)")
                self.print_details("EMA_SELL4", detail)

            # time.sleep(20)


    async def buy_order(self):
        if self.NoTrade:
            data = self.prepare_order_data("Buy", self.current_price)
            print('data of the grid', data)
            logger.info('data of the grid', data)
            self.count = 1
            self.current_side = "Buy"
            self.PrevReason = self.reason
            self.reason = 'Bybit Custom BUY'
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)('BUY', 'Bybit CUSTOM BUY ORDER', details=detail)
            self.print_details("C_BUY", detail)
            self.update_conditions()
        else:
            print("Already Bought")
            logger.info("Already Bought")

    async def sell_order(self):
        if self.NoTrade:
            data = self.prepare_order_data("Sell", self.current_price)
            print('data of the grid', data)
            logger.info('data of the grid', data)
            self.count = 1
            self.current_side = "Sell"
            self.PrevReason = self.reason
            self.reason = 'Bybit Custom SELL'
            detail = self.calculated_grid_orders(data)
            await sync_to_async(self.save_order)('SELL', 'Bybit CUSTOM SELL ORDER', details=detail)
            self.print_details("C_SELL", detail)
            self.update_conditions()
        else:
            print("Already Sold")
            logger.info("Already Sold")

    async def close_custom_order(self):
        if self.BuyTrade or self.SellTrade:
            detail = await sync_to_async(self.close_all_orders)(description= "Bybit CUSTOM CLOSE BUY ORDER")
            self.print_details("C_CLOSE_BUY", detail)
        else:
            print('No Trade in Record')
            logger.info('No Trade in Record')



    def SendTelegramMessage(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.user.Token}/sendMessage?chat_id={self.user.Bot_ID}&text={message}"
            print('Telegram Message Sent')
            logger.info('Telegram Message Sent')
            requests.get(url).json()
        except Exception as e:
            print(f"cannot send Telegram message {e}")
            logger.info(f"cannot send Telegram message {e}")



    def SendTelegramChannelMessage(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.user.Channel_Token}/sendMessage?chat_id={self.user.Channel_Bot_ID}&text={message}"
            print('Telegram Channel Message Sent')
            logger.info('Telegram Channel Message Sent')
            requests.get(url).json()
        except Exception as e:
            print(f"cannot send Telegram Channel message {e}")
            logger.info(f"cannot send Telegram Channel message {e}")



    def prepare_order_data(self, side, current_price):
        config = self.pair_config
        if self.pair_config['Amount_Type'] == "dollar":
            # Keep original dollar values for market orders
            quantity_dollar = config['quantity']
            favor_level_qty_dollar = config['favor_level_qty']
            against_level_qty_dollar = config['against_level_qty']
            
            # Convert to coins for limit orders
            quantity = round(config['quantity'] / current_price, 4)
            favor_level_qty = round(config['favor_level_qty'] / current_price, 4)
            against_level_qty = round(config['against_level_qty'] / current_price, 4)
            print('dollar calculated - coins:', quantity, favor_level_qty, against_level_qty)
            logger.info(f'dollar calculated - coins: {quantity}, {favor_level_qty}, {against_level_qty}')
        else:
            # For coin type, everything is in coins
            quantity = config['quantity']
            favor_level_qty = config['favor_level_qty']
            against_level_qty = config['against_level_qty']
            # No dollar values needed
            quantity_dollar = None
            favor_level_qty_dollar = None
            against_level_qty_dollar = None
            print('coin calculated', quantity, favor_level_qty, against_level_qty)
            logger.info('coin calculated', quantity, favor_level_qty, against_level_qty)

        quantity = float(self.exchange.amount_to_precision(self.symbol, quantity))
        favor_level_qty = float(self.exchange.amount_to_precision(self.symbol, favor_level_qty))
        against_level_qty = float(self.exchange.amount_to_precision(self.symbol, against_level_qty))

        data = {
            "category": 'futures',
            "symbol": self.symbol,
            "Order_Type": config['Order_Type'],
            "side": side,
            "qty": quantity,  # coins
            "qty_dollar": quantity_dollar,  # original dollar value (or None for coin type)
            "price": current_price,
            "favor_levels": config['favor_levels'],
            "against_levels": config['against_levels'],
            "favor_level_qty": favor_level_qty,  # coins
            "against_level_qty": against_level_qty,  # coins
            "favor_level_qty_dollar": favor_level_qty_dollar,
            "against_level_qty_dollar": against_level_qty_dollar,
            "favor_level_difference": config['favor_level_difference'],
            "against_level_difference": config['against_level_difference']
        }
        return data

    def fetch_current_price(self):
        """Fetch the current market price asynchronously."""
        ticker, symbol = self.exchange.fetch_ticker, self.symbol
        self.current_price = ticker(symbol)["last"]
        thread_id = threading.get_ident()  # Get the thread ID
        logger.info(f"Thread ID: {thread_id} | Fetched current price: {self.current_price}")
        return self.current_price

    def save_order(self, side, description, details):
        """Place an order and save it to the database."""
        indicator = Indicator.objects.create(
            Pair=self.symbol,
            user=self.user,
            EMA=self.EMA,
            RSI=self.RSI,
            Prev_RSI=self.PrevRSI,
            Color=self.RSI_color,
            Prev_Color=self.RSI_prev_color,
            BB=self.BB,
            TSI=self.TSI,
            ADX=self.ADX
        )
        order = Order.objects.create(
            Pair=self.symbol,
            user=self.user,
            PairConfig_id=self.pair_config["id"],
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
        logger.info(f"Placed order: {order}")
        return order

    def get_latest_order(self):
        return Order.objects.filter(Pair=self.symbol).last()

    # old working code
    # def create_order(self, order_type, side, quantity, price):
    #     try:
    #         # data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
    #         # converted normal create_order function to create_order_with_cost
    #         if self.pair_config['Amount_Type'] == "dollar":
    #             if order_type == 'market':
    #                 data = self.exchange.create_market_order_with_cost(self.symbol, side, self.pair_config['quantity'], params={'category': 'linear'})
    #             elif order_type == 'limit':
    #                 data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
    #         else:
    #             data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
    #         print(f'Order type: {order_type} - Side: {side} - Quantity: {quantity} - Price: {price}')
    #         return data
    #     except Exception as e:
    #         print(f"cannot create order {e}")
    #         logger.info(f"cannot create order {e}")

    def create_order(self, order_type, side, quantity, price):
        try:
            # data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            # converted normal create_order function to create_order_with_cost
            if self.pair_config['Amount_Type'] == "dollar":
                if order_type == 'market':
                    data = self.exchange.create_market_order_with_cost(self.symbol, side, quantity, params={'category': 'linear'})
                elif order_type == 'limit':
                    data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            else:
                data = self.exchange.create_order(self.symbol, order_type, side, quantity, price, params={'category': 'linear'})
            print(f'Order type: {order_type} - Side: {side} - Quantity: {quantity} - Price: {price}')
            logger.info(f'Order type: {order_type} - Side: {side} - Quantity: {quantity} - Price: {price}')
            return data
        except Exception as e:
            print(f"cannot create order {e}")
            logger.info(f"cannot create order {e}")



    def close_open_order(self, description):
        try:
            # position = self.exchange.fetch_position(symbol=self.symbol, params={'category': 'linear'})
            closing_symbol = self.symbol.replace('/', '')
            position = self.exchange.fetch_positions(symbols=closing_symbol, params={'category': 'linear'})
            # logger.info(position)
            size = float(position[0]['contracts'])
            self.Unrealized_Pnl = float((position[0]['unrealizedPnl']))

            side = position[0]['side']
            if self.pair_config['SLTP_Type'] == 'percentage':
                self.Percentage = self.Unrealized_Pnl / size * 1000
                self.last_trade_pnl = self.Unrealized_Pnl

            message = f"User: {self.user.username}\nBybit \nPair: {self.symbol} {datetime.now(pytz.timezone('Asia/Karachi'))}\n Closing Position\n {position}"
            channel_message = f"""Timezone: GMT+5 \n Time: {datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nSymbol: {self.symbol} \nClosing Position: {position} """
            self.SendTelegramMessage(message)
            self.SendTelegramChannelMessage(channel_message)
            if side == 'short':
                try:
                    detail = self.exchange.create_order(symbol=closing_symbol, type='market', amount=size, side='buy',params={'reduceOnly': True})
                    self.save_order(side, description, detail)
                    return detail
                except Exception as e:
                    print('Creating Order Failed at line 509', e)
                    logger.info('Creating Order Failed at line 509', e)

                print('====Bybit Short Order Closed ==== \n')
                logger.info('====Bybit Short Order Closed ==== \n')

            elif side == 'long':
                try:
                    detail = self.exchange.create_order(symbol=closing_symbol, type='market', amount=size, side='sell',params={'reduceOnly': True})
                    self.save_order(side, description, detail)
                    return detail
                except Exception as e:
                    print('Creating Order Failed at line 519', e)
                    logger.info('Creating Order Failed at line 519', e)

                print('====Bybit Long Order Closed ==== \n')
                logger.info('====Bybit Long Order Closed ==== \n')

        except Exception as e:
            print("No position found", e)
            logger.info("No position found", e)
            return None

    # old code running
    # def close_all_orders(self, description):
    #     self.exchange.cancel_all_orders(symbol=self.symbol)
    #     position = self.close_open_order(description)
    #     self.reset_trading_state()
    #     self.reason = description
    #     print(f'All BYBIT Orders Closed: {description}')
    #     return position

    def close_all_orders(self, description):
        logger.info(f"cancelling all limit orders of self.symbol: {self.symbol}, pair_config['pair_symbol']: {self.pair_config['pair_symbol']}")
        closing_symbol = self.symbol.replace('/', '')
        self.reset_trading_state()
        self.exchange.cancel_all_orders(symbol=closing_symbol)
        position = self.close_open_order(description)
        self.reason = description
        print(f'All BYBIT Orders Closed: {description}')
        logger.info(f'All BYBIT Orders Closed: {description}')
        return position





    def qty(self):
        if self.pair_config['Amount_Type'] == "dollar":
            quantity = round(self.pair_config['quantity'] / self.current_price, 4)
            favor_level_qty = round(self.pair_config['favor_level_qty'] / self.current_price, 4)
            against_level_qty = round(self.pair_config['against_level_qty'] / self.current_price, 4)
            print('dollar calculated', quantity, favor_level_qty, against_level_qty)
            logger.info('dollar calculated', quantity, favor_level_qty, against_level_qty)
            return quantity, favor_level_qty, against_level_qty
        else:
            quantity = self.pair_config['quantity']
            favor_level_qty = self.pair_config['favor_level_qty']
            against_level_qty = self.pair_config['against_level_qty']
            print('coin calculated', quantity, favor_level_qty, against_level_qty)
            logger.info('coin calculated', quantity, favor_level_qty, against_level_qty)
            return quantity, favor_level_qty, against_level_qty


    def calculated_grid_orders(self, data):
        self.bot_running = True
        self.monitoring = True
        print(f'Bybit Calculating Grids for {data["symbol"]}')
        logger.info(f'Bybit Calculating Grids for {data["symbol"]}')

        symbol = data['symbol']
        side = data['side']
        qty = data['qty']
        print(f'quantity: {qty} - type {type(qty)}')
        price = data['price']
        favor_level_qty = data['favor_level_qty']
        against_level_qty = data['against_level_qty']
        print(f"Grid data: {data['symbol']} - {data['Order_Type']} - {side} - {qty} - {price}")
        logger.info(f"Grid data: {data['symbol']} - {data['Order_Type']} - {side} - {qty} - {price}")

        # Open initial order
        initial_order = None
        try:
            if self.pair_config['Amount_Type'] == "dollar":
                # Use the ORIGINAL dollar value for market orders with cost
                qty_dollar = data['qty_dollar']
                print(f'pair config amount type dollar {self.pair_config["Amount_Type"]} - cost in dollars:{qty_dollar} - side: {side}')
                logger.info(f'pair config amount type dollar {self.pair_config["Amount_Type"]} - cost in dollars:{qty_dollar} - side: {side}')
                if side =='Buy':
                    initial_order = self.exchange.create_market_buy_order_with_cost(self.symbol, cost=qty_dollar, params={'category': 'linear'})
                    print('initial market buy order with dollar cost', initial_order)
                    logger.info('initial market buy order with dollar cost', initial_order)
                elif side =='Sell':
                    initial_order = self.exchange.create_market_sell_order_with_cost(self.symbol, cost=qty_dollar, params={'category': 'linear'})
                    print('initial market sell order with dollar cost', initial_order)
                    logger.info('initial market sell order with dollar cost', initial_order)

            elif self.pair_config['Amount_Type'] == "coin":
                # Use coin quantity for normal orders
                print(f'pair config amount type coin - quantity in coins:{qty} - side: {side}')
                logger.info(f'pair config amount type coin - quantity in coins:{qty} - side: {side}')
                initial_order = self.create_order(order_type=self.pair_config['Order_Type'], side=side, quantity=qty, price=price)
            else:
                print('neither dollar nor coin', self.pair_config['Amount_Type'])
                logger.info('neither dollar nor coin', self.pair_config['Amount_Type'])
        except Exception as e:
            print('Creating Order Failed at line 572', e)
            logger.info('Creating Order Failed at line 572', e)

        favor_levels, against_levels = self.calculate_grids(side)
        # updating levels on global variable for indicator page
        self.favor_lvl, self.against_lvl = favor_levels, against_levels

        if side.lower() == 'buy':

            # Open grid orders
            for level in favor_levels:
                level_price = float(level)
                # Place sell orders at favor levels
                try:
                    print(f'quantity: {qty} - type {type(qty)}')
                    self.create_order('limit', 'sell', favor_level_qty, level_price)
                except Exception as e:
                    print('Creating Order Failed at line 587', e)
                    logger.info('Creating Order Failed at line 587', e)

            for level in against_levels:
                level_price = float(level)
                # Place buy orders at against levels
                try:
                    self.create_order('limit', 'buy', against_level_qty, level_price)
                except Exception as e:
                    print('Creating Order Failed at line 595', e)
                    logger.info('Creating Order Failed at line 595', e)

        if side.lower() == 'sell':

            for level in favor_levels:
                level_price = float(level)
                # Place buy orders at favor levels
                try:
                    self.create_order('limit', 'buy', favor_level_qty, level_price)
                except Exception as e:
                    print('Creating Order Failed at line 605', e)
                    logger.info('Creating Order Failed at line 605', e)

            for level in against_levels:
                level_price = float(level)
                # Place sell order at against levels
                try:
                    self.create_order('limit', 'sell', against_level_qty, level_price)
                except Exception as e:
                    print('Creating Order Failed at line 613', e)
                    logger.info('Creating Order Failed at line 613', e)

        # Start monitoring orders in a separate thread
        # waiting for all orders to take place before monitoring
        time.sleep(3)
        monitoring_thread = threading.Thread(
            target=self.monitor_grid_orders, 
            args=(side, price, favor_levels, against_levels, favor_level_qty, against_level_qty),
            name=f"GridMonitor-{self.symbol}-{side}"
        )
        monitoring_thread.daemon = True  # Thread will die when main process dies
        monitoring_thread.start()
        self.monitoring_threads.append(monitoring_thread)

        return initial_order

    def monitor_grid_orders(self, side, entry_price, favor_levels, against_levels, favor_level_qty, against_level_qty):
        last_favor_level = None
        last_against_level = None
        logger.info('Monitoring Bybit Grid Orders.')
        self.current_price = self.fetch_current_price()
        print(f"Bybit  {self.symbol} Current price: {self.current_price}   CurrentSide : {side} on KEYPAIR {self.symbol}, owner ={self.user.username}")
        logger.info(f"Bybit  {self.symbol} Current price: {self.current_price}   CurrentSide : {side} on KEYPAIR {self.symbol}, owner ={self.user.username}")

        # --- NEW: maps to track orders by id and price ---
        favor_order_map = {}  # price -> order_id for favor side orders (the ones placed initially as grid)
        against_order_map = {}  # price -> order_id for against side orders

        # Helper to place an order and register mapping
        def place_and_register(price, ord_side, qty, register_map):
            try:
                resp = self.create_order('limit', ord_side, qty, float(price))
                logger.info(f"order response: {resp}\n")
                # assume resp contains an 'id' (order id). If your create_order returns order object differently adapt here.
                order_id = resp.get('id') if isinstance(resp, dict) else getattr(resp, 'id', None)
                if order_id is None:
                    # fallback: try to inspect resp for order id keys
                    order_id = resp.get('orderId') if isinstance(resp, dict) else None
                if order_id is None:
                    # if create_order doesn't return id, try to find the order by price in open orders (best-effort)
                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                    logger.info(f'fetched open orders \n')
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

        # --- INITIALIZE maps with currently-open grid orders (try best-effort lookup) ---
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
                    # depending on initial side, sell may be favor or against
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
                # fetch open orders once per iteration
                open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                # logger.info(f'open orders in monitoring')
                current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                # logger.info(f'Current buy prices data: {current_buy_prices}\n')
                # logger.info(f'Current sell prices data: {current_sell_prices}\n')
                # function to check if an order id is filled (order-based)
                def is_filled(order_id):
                    if not order_id:
                        return False
                    try:
                        # fetch order status directly
                        o = self.exchange.fetch_order(order_id, symbol=self.symbol, params={'category': 'linear'})
                        logger.info(f' fetch order in "is_filled" function {o}')
                        status = o.get('status') or o.get('state')
                        # ccxt uses 'closed' or 'canceled' etc. Treat 'closed' as filled.
                        if isinstance(status, str) and status.lower() in ('closed', 'filled', 'filled_partially'):  # include partially maybe
                            # If partially filled you may want to inspect 'filled' vs 'amount'
                            return True
                        return False
                    except Exception:
                        # fallback: if not available, check presence in open orders (if not present -> probably filled)
                        try:
                            # if the order id is not in open_orders, assume done (best-effort)
                            for o2 in open_orders:
                                if (o2.get('id') == order_id) or (o2.get('orderId') == order_id) or (o2.get('clientOrderId') == order_id):
                                    return False
                            return True
                        except Exception:
                            return False

                # --- Process favor orders (these are the grid that, when filled, should cause you to create new against orders) ---
                # Iterate over a copy of keys to avoid mutation issues
                favor_keys = sorted(list(favor_order_map.keys()), reverse=reverse_for_favor)
                for price in favor_keys:
                    order_id = favor_order_map.get(price)
                    # if order filled -> handle
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"Favor order filled at {executed_level} id={order_id}")
                        # remove from map
                        favor_order_map.pop(price, None)
                        # Update your favor_lvl / against_lvl lists similarly to your old logic
                        try:
                            # remove price from favor_levels lists if present (match by value)
                            if price in [float(x) for x in favor_levels]:
                                for i, v in enumerate(favor_levels):
                                    if float(v) == price:
                                        favor_levels.pop(i)
                                        break
                        except Exception:
                            pass

                        # Decide where to insert entry_price and create order (keep your existing logic)
                        # Use last_favor_level logic from your original code but based on numeric floats
                        if last_favor_level is not None and executed_level >= float(last_favor_level):
                            # insert entry price at right level
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                # create buy at against_levels[0] (your logic)
                                # But first ensure we compute the price we want to place the buy at
                                place_price = float(entry_price)
                                ord_side = 'buy' if side.lower() == 'buy' else 'sell'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, against_level_qty, against_order_map)
                                print('Buy @' if side.lower() == 'buy' else 'Sell @', place_price)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - Buy @ {place_price}' if side.lower() == 'buy' else f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - Sell @ {place_price}')
                                if new_oid:
                                    against_levels.append(place_price)
                                    against_levels.sort(reverse=reverse_for_against)
                                    self.against_lvl = against_levels[:]
                                    open_orders = self.exchange.fetch_open_orders(symbol=self.symbol, params={'category': 'linear'})
                                    current_buy_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'buy')
                                    current_sell_prices = set(float(order['price']) for order in open_orders if order['side'].lower() == 'sell')
                            # update last & entry
                            last_favor_level = executed_level
                            entry_price = executed_level
                        else:
                            if entry_price not in favor_levels and entry_price not in against_levels:
                                # place buy at against_levels[0] if exists
                                place_price = float(entry_price)
                                ord_side = 'buy' if side.lower() == 'buy' else 'sell'
                                if ord_side == 'buy':
                                    if float(place_price) in current_buy_prices:
                                        continue
                                else:
                                    if float(place_price) in current_sell_prices:
                                        continue
                                new_oid = place_and_register(place_price, ord_side, against_level_qty, against_order_map)
                                print('Buy @' if side.lower() == 'buy' else 'Sell @', place_price)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - Buy @ {place_price}' if side.lower() == 'buy' else f'{datetime.now(pytz.timezone("Asia/Karachi"))} Against Levels - Sell @ {place_price}')
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

                # --- Process against orders (when filled create favor orders) ---
                against_keys = sorted(list(against_order_map.keys()), reverse=reverse_for_against)
                for price in against_keys:
                    order_id = against_order_map.get(price)
                    if is_filled(order_id):
                        executed_level = float(price)
                        logger.info(f"{datetime.now(pytz.timezone('Asia/Karachi'))} Against order filled at {executed_level} id={order_id}")
                        against_order_map.pop(price, None)
                        # remove from against lists if present
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
                                print('Sell @' if side.lower() == 'buy' else 'Buy @', place_price)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - Sell @ {place_price}' if side.lower() == 'buy' else f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - Buy @ {place_price}')
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
                                print('Sell @' if side.lower() == 'buy' else 'Buy @', place_price)
                                logger.info(f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - Sell @ {place_price}' if side.lower() == 'buy' else f'{datetime.now(pytz.timezone("Asia/Karachi"))} Favor Levels - Buy @ {place_price}')
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
                print(f'Error in monitor_grid_orders: {e}')
                logger.error(f'Error in monitor_grid_orders: {e}')
                time.sleep(2)

# needs to fix the "side"
    def monitor_lossProfit(self, side):
        loss_profit_percentage = 0.0
        time.sleep(4)
        message = f"User: {self.user.username}\nPair: {self.symbol}\n{datetime.now(pytz.timezone('Asia/Karachi'))}\nCurrent Price: {self.current_price}\nEMA: {self.EMA}\nRSI: {self.RSI}\nPrevRSI: {self.PrevRSI}\nRSI_Color: {self.RSI_color}\nBB: {self.BB}\nCurrent Side: {self.current_side}\nCount: {self.count}"

        while self.monitoring and not self._stop_event.is_set():
            # if self.pair_config['SL_Exit'] is not None:
            try:
                loss_profit_percentage = self.check_lossProfit_percent()
                if loss_profit_percentage is None:
                    loss_profit_percentage = 0.0

                elif self.pair_config['SL_Exit'] == 'sl' or self.pair_config['SL_Exit'] == 'both':
                    if loss_profit_percentage <= self.pair_config['Stop_Loss']:
                        reason = "SL"
                        message = message + reason
                        self.SendTelegramMessage(message)
                        channel_message = f"Timezone: GMT+ \nTime: {datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nSymbol: {self.symbol} \nClosing Position \nStop Loss Price: ({self.current_price}) "
                        self.SendTelegramChannelMessage(channel_message)

                        self.close_all_orders('SL hit Position and closed')
                        self.print_details("SL", loss_profit_percentage)

                if self.pair_config['SL_Exit'] == 'tp' or self.pair_config['SL_Exit'] == 'both':
                    if loss_profit_percentage >= self.pair_config['Take_Profit']:
                        reason = "TP"
                        message = message + reason
                        self.SendTelegramMessage(message)
                        channel_message = f"""Timezone: GMT+ \nTime: {datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nSymbol: {self.symbol} \nClosing Position\n Stop Loss Price:({self.current_price}) """
                        self.SendTelegramChannelMessage(channel_message)

                        self.close_all_orders('TP hit Position and closed')
                        self.print_details("TP", loss_profit_percentage)
                        print("TP hit Buy Position and closed")
                        logger.info("TP HIT!!! - Buy Position and closed\n")
            except Exception as e:
                print(f"Loss Profit Exeption: {str(e)}")
                logger.info(f"Loss Profit Exeption: {str(e)}")


            # else:
            #     try:
            #         loss_profit_percentage = self.check_lossProfit_percent()
            #         if loss_profit_percentage is None:
            #             loss_profit_percentage = 0.0
            #         else:
            #             self.Percentage = loss_profit_percentage
            #     except Exception as e:
            #         print(f"Loss Profit Exception: {str(e)}")
            #         logger.info(f"Loss Profit Exception: {str(e)}")
            # Use interruptible sleep
            if self._stop_event.wait(timeout=5.0):
                break  # Stop event was set



    def check_lossProfit_percent(self):
        # order = Order.objects.filter(Pair=self.symbol).last()
        exchange = self._initialize_exchange()
        try:
            # position = exchange.fetch_positions(symbols=[self.symbol,], params={'category': 'linear'})
            position = exchange.fetch_position(symbol=self.symbol, params={'category': 'linear'})

            # print(position)
            # amount = float(position[0]['info']['positionAmt'])
            # unrealizedPnl = float(position[0]['unrealizedPnl'])
            # initialMargin = float(position[0]['info']['initialMargin'])
            # total_cost = entry_price * amount
            # percentage = (unrealizedPnl / total_cost) * 100
            if position:
                size = float(position['notional'])
                pnl = float((position['unrealizedPnl']))
                self.Unrealized_Pnl = pnl
                self.Percentage = pnl / size * 1000
            else:
                print(f"No position found on {self.symbol} of User: {self.user.username}")
                logger.info(f"No position found on {self.symbol} of User: {self.user.username}")
        except Exception as e:
            print(f"Check Loss Profit Exception: {str(e)}")
            logger.info(f"Check Loss Profit Exception: {str(e)}")
            self.Unrealized_Pnl = 0.0
            self.Percentage = 0.0

        print(f'\nUser: {self.user.username}    Pair: {self.symbol}   Percentage: {self.Percentage}   PNL: {self.Unrealized_Pnl}  Price: {self.current_price}')
        logger.info(f'\nUser: {self.user.username}    Pair: {self.symbol}   Percentage: {self.Percentage}   PNL: {self.Unrealized_Pnl}  Price: {self.current_price}')
        if self.pair_config['SLTP_Type'] == 'percentage':
            return self.Percentage
        elif self.pair_config['SLTP_Type'] == 'dollars':
            return self.Unrealized_Pnl

    def calculate_grids(self, side):
        favor_levels = []
        against_levels = []
        if side.lower() == 'buy':
            for levels in range(self.pair_config["favor_levels"]):
                # entryPrice * (1 + (i + 1) * perdiffav / 100))
                favor_levels.append(
                    round(self.current_price * (1 + (levels + 1) * self.pair_config['favor_level_difference'] / 100), 6))
            for levels in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 - (levels + 1) * self.pair_config['against_level_difference'] / 100), 6))

        if side.lower() == 'sell':
            for levels in range(self.pair_config['favor_levels']):
                # entryPrice * (1 + (i + 1) * perdiffav / 100))
                favor_levels.append(
                    round(self.current_price * (1 - (levels + 1) * self.pair_config['favor_level_difference'] / 100), 6))
            for levels in range(self.pair_config['against_levels']):
                against_levels.append(
                    round(self.current_price * (1 + (levels + 1) * self.pair_config['against_level_difference'] / 100), 6))

        # print('\nfav levels: ', favor_levels)
        # print('\nagainst levels: ', against_levels)
        return favor_levels, against_levels



    # to print Details and Log them + sending data to telegram
    def print_details(self, data, details, percentage=None):
        if data == 'BUY1':
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA + RSI BUY LONG (CASE1) =====\n\n   {self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA + RSI BUY LONG (CASE1) =====\n\n----   {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA + RSI BUY LONG (CASE1) =====\n\nUser: {self.user.username}\n  {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \nTP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == 'BUY2':
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA + BOLLINGER BANDS BUY LONG (CASE2) =====\n\n  {self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA + BOLLINGER BANDS BUY LONG (CASE2) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA + BOLLINGER BANDS BUY LONG (CASE2) =====\n\nUser: {self.user.username}\n  {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == 'BUY3':
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} BOLLINGER BANDS + RSI BUY LONG (CASE3) =====\n\n  {self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} BOLLINGER BANDS + RSI BUY LONG (CASE3) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} BOLLINGER BANDS + RSI BUY LONG (CASE3) =====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "BUY4":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY RSI BUY LONG (CASE4) =====\n\n {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY RSI BUY LONG (CASE4) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} ONLY RSI BUY LONG (CASE4) =====\n\nUser: {self.user.username}\n  {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "BUY5":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY BOLLINGER BANDS  BUY LONG (CASE5) =====\n\n {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY BOLLINGER BANDS  BUY LONG (CASE5) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} ONLY BOLLINGER BANDS  BUY LONG (CASE5) =====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "BUY6":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA RSI BOLLINGER BANDS  BUY LONG (CASE6) =====\n\n {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA RSI BOLLINGER BANDS  BUY LONG (CASE6) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA RSI BOLLINGER BANDS  BUY LONG (CASE6) =====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_BUY1":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ==== {self.symbol} TP-BUY Position Bollinger Band TP (TP CASE1)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ==== {self.symbol} TP-BUY Position Bollinger Band TP (TP CASE1)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} TP-BUY Position Bollinger Band TP (TP CASE1)= =====\n\nUser: {self.user.username}\n  {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: @{self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_BUY2":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} TP-BUY RSI Upper Peak (TP CASE2)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} TP-BUY RSI Upper Peak (TP CASE2)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} TP-BUY RSI Upper Peak (TP CASE2) =====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: @{self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_BUY3":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} TP-BUY BOLLINGER BANDS + RSI (TP CASE3)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} TP-BUY BOLLINGER BANDS + RSI (TP CASE3)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} TP-BUY BOLLINGER BANDS + RSI (TP CASE3) =====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: @{self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_BUY4":
            print(
                f"-- TP-BUY Position-CASE4--- - closed Buy Order @ \n\n{datetime.now(pytz.timezone('Asia/Karachi'))}")
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol}  EMA + Bollinger Bands -- (TP-BUY-CASE 4)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol}  EMA + Bollinger Bands -- (TP-BUY-CASE 4)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f"  ====== {self.symbol}  EMA + Bollinger Bands -- (TP-BUY-CASE 4)=====\n\nUser: {self.user.username}\n {self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: @{self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SL_BUY":
            print('Checking SL Buy Case \n')
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} SL-BUY =====\n\n  Loss-Profit-Percentage: {percentage} -  {self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} SL-BUY =====\n\n   Loss-Profit-Percentage: {percentage} -  {self.get_indicator_data()}\n")

            print("SL hit - Buy Position  closed")
            logger.info("SL hit - Buy Position  closed\n")
            message = f"====== {self.symbol} SL-BUY =====\n\nUser: {self.user.username}  \nLoss-Profit-Percentage: {percentage}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN CLOSE BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nSL HIT: @{self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL1":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} EMA + RSI SELL SHORT  (CASE1) =====\n\n  - {self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} EMA + RSI SELL SHORT  (CASE1) =====\n\n  - {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA + RSI SELL SHORT  (CASE1) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL2":
            logger.info(
                f" \n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} EMA + BOLLINGER BANDS SELL SHORT  (CASE2) =====\n\n - {self.get_indicator_data()}\n")
            print(
                f" \n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} EMA + BOLLINGER BANDS SELL SHORT  (CASE2) =====\n\n - {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA + BOLLINGER BANDS SELL SHORT  (CASE2) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL3":
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} BOLLINGER BANDS + RSI SELL SHORT (CASE3) =====\n\n  {self.get_indicator_data()}\n")
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} BOLLINGER BANDS + RSI SELL SHORT (CASE3) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} BOLLINGER BANDS + RSI SELL SHORT (CASE3) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL4":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY RSI SELL SHORT  (CASE4) =====\n\n {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY RSI SELL SHORT  (CASE4) =====\n\n {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} ONLY RSI SELL SHORT  (CASE4) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL5":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY BOLLINGER BANDS SELL SHORT  (SELL CASE5) =====\n\n  {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} ONLY BOLLINGER BANDS SELL SHORT  (SELL CASE5) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} ONLY BOLLINGER BANDS SELL SHORT  (SELL CASE5) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nOPEN SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SELL6":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA RSI BOLLINGER BANDS SELL SHORT  (SELL CASE6) =====\n\n  {self.get_indicator_data()}\n")
            logging.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))} ====== {self.symbol} EMA RSI BOLLINGER BANDS SELL SHORT  (SELL CASE6) =====\n\n  {self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA RSI BOLLINGER BANDS SELL SHORT  (SELL CASE6) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nSELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nMargin Usage: 1% of Capital \nLEVERAGE: Cross 10X \nSL: {self.pair_config['Stop_Loss']} PNL \n TP: {self.favor_lvl[3]}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_SELL1":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} RSI  SELL TP (CASE1)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} RSI  SELL TP (CASE1)=====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} RSI  SELL TP (CASE1) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_SELL2":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} BOLLINGER BANDS + RSI SELL TP (CASE2) =====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} BOLLINGER BANDS + RSI SELL TP (CASE2) =====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} BOLLINGER BANDS + RSI SELL TP (CASE2) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))}\nExchange: Bybit  \nCLOSE SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_SELL3":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} ONLY BOLLINGER BANDS SELL TP (CASE3) =====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} ONLY BOLLINGER BANDS SELL TP (CASE3) =====\n\n Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} ONLY BOLLINGER BANDS SELL TP (CASE3) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "TP_SELL4":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} EMA + BOLLINGER BANDS SELL TP (CASE4) =====\n\nCurrentPrice: {self.current_price} Loss-Profit-Percentage: {percentage}   Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}   ====== {self.symbol} EMA + BOLLINGER BANDS + RSI2 SELL TP (CASE4) =====\n\nCurrentPrice: {self.current_price} Loss-Profit-Percentage: {percentage} Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} EMA + BOLLINGER BANDS SELL TP (CASE4) =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nTP HIT: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "SL_SELL":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} STOP LOSS OF SELL =====\n\n  CurrentPrice: {self.current_price} Loss-Profit-Percentage: {percentage}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} STOP LOSS OF SELL =====\n\n  CurrentPrice: {self.current_price} Loss-Profit-Percentage: {percentage}\n\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} STOP LOSS OF SELL =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCLOSE SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nSL HIT: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "C_BUY":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM BUY =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM BUY =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} CUSTOM BUY =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCUSTOM BUY/LONG \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nCUSTOM BUY @: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)


        elif data == "C_SELL":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM SELL =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM SELL =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} CUSTOM SELL =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)
            channel_message = f"""Timezone: UTC+5 \n{datetime.now(pytz.timezone('Asia/Karachi'))} \nExchange: Bybit \nCUSTOM SELL/SHORT \nSYMBOL: {self.symbol} \nPrice: {self.current_price} \nCUSTOM SELL @: {self.current_price}"""
            self.SendTelegramChannelMessage(channel_message)

        elif data == "C_CLOSE_BUY":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM CLOSE BUY =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM CLOSE BUY =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} CUSTOM CLOSE BUY =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)

        elif data == "C_CLOSE_SELL":
            print(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM CLOSE SELL =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            logger.info(
                f"\n\n{datetime.now(pytz.timezone('Asia/Karachi'))}  ====== {self.symbol} CUSTOM CLOSE SELL =====\n\n  CurrentPrice: {self.current_price}\n{self.get_indicator_data()}\n")
            message = f" ====== {self.symbol} CUSTOM CLOSE SELL =====\n\nUser: {self.user.username}  \n{self.get_indicator_data()}\n\nDetails: {details}\n"
            self.SendTelegramMessage(message)





