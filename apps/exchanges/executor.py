# trading/exchanges/executor.py
"""
Factory pattern for exchange-specific order execution.
Each exchange has its own executor class with exchange-specific API calls.
"""

import logging
from typing import Dict, Any
from apps.exchanges.models import ExchangeCredentials
from core.utils import decrypt_api_key

logger = logging.getLogger('trading')


class ExchangeExecutor:
    """
    Factory class that routes order execution to exchange-specific executors.
    """

    @staticmethod
    def execute_order(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        """
        Execute an order on the specified exchange.

        Args:
            order_data: {
                'symbol': 'BTC/USDT',
                'side': 'buy',
                'type': 'market',
                'amount': 1.5,
                'price': 45000 (optional for limit)
            }
            credentials: ExchangeCredentials instance

        Returns:
            Order execution result
        """
        exchange_name = credentials.exchange_name.lower()

        try:
            if exchange_name == 'binance':
                return BinanceExecutor.execute(order_data, credentials)
            elif exchange_name == 'bybit':
                return BybitExecutor.execute(order_data, credentials)
            elif exchange_name == 'okx':
                return OKXExecutor.execute(order_data, credentials)
            elif exchange_name == 'mexc':
                return MEXCExecutor.execute(order_data, credentials)
            elif exchange_name == 'alpaca':
                return AlpacaExecutor.execute(order_data, credentials)
            else:
                raise ValueError(f"Unsupported exchange: {exchange_name}")

        except Exception as e:
            logger.error(f"Error executing order on {exchange_name}: {e}")
            raise


class BaseExecutor:
    """Base class for all exchange executors"""

    @staticmethod
    def _get_decrypted_credentials(credentials: ExchangeCredentials) -> Dict[str, str]:
        """Decrypt and return API credentials"""
        return {
            'api_key': decrypt_api_key(credentials.api_key),
            'secret_key': decrypt_api_key(credentials.secret_key),
            'passphrase': decrypt_api_key(credentials.passphrase) if credentials.passphrase else None,
            'is_testnet': credentials.is_testnet,
        }


class BinanceExecutor(BaseExecutor):
    """Binance-specific order execution using python-binance"""

    @staticmethod
    def execute(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        from binance.client import Client

        creds = BaseExecutor._get_decrypted_credentials(credentials)

        # Use testnet if configured
        if creds['is_testnet']:
            client = Client(
                api_key=creds['api_key'],
                api_secret=creds['secret_key'],
                testnet=True
            )
        else:
            client = Client(
                api_key=creds['api_key'],
                api_secret=creds['secret_key']
            )

        symbol = order_data['symbol'].replace('/', '')  # BTC/USDT -> BTCUSDT
        side = order_data['side'].upper()  # buy -> BUY
        order_type = order_data['type']
        quantity = float(order_data['amount'])

        try:
            if order_type == 'market':
                if side == 'BUY':
                    result = client.order_market_buy(
                        symbol=symbol,
                        quantity=quantity
                    )
                else:
                    result = client.order_market_sell(
                        symbol=symbol,
                        quantity=quantity
                    )
            elif order_type == 'limit':
                price = float(order_data['price'])
                if side == 'BUY':
                    result = client.order_limit_buy(
                        symbol=symbol,
                        quantity=quantity,
                        price=price
                    )
                else:
                    result = client.order_limit_sell(
                        symbol=symbol,
                        quantity=quantity,
                        price=price
                    )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            return {
                'order_id': result['orderId'],
                'symbol': result['symbol'],
                'status': result['status'],
                'executed_qty': result['executedQty'],
                'price': result.get('avgPrice', result.get('price')),
                'side': result['side'],
                'type': result['type'],
                'transact_time': result['transactTime'],
            }

        except Exception as e:
            logger.error(f"Binance execution failed: {e}")
            raise


class BybitExecutor(BaseExecutor):
    """Bybit-specific order execution using pybit"""

    @staticmethod
    def execute(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        from pybit.unified_trading import HTTP

        creds = BaseExecutor._get_decrypted_credentials(credentials)

        # Initialize session
        session = HTTP(
            testnet=creds['is_testnet'],
            api_key=creds['api_key'],
            api_secret=creds['secret_key'],
        )

        symbol = order_data['symbol']
        side = order_data['side'].capitalize()  # buy -> Buy
        order_type = order_data['type']
        qty = float(order_data['amount'])

        try:
            if order_type == 'market':
                result = session.place_order(
                    category="linear",  # or "spot" depending on market type
                    symbol=symbol,
                    side=side,
                    orderType="Market",
                    qty=qty,
                )
            elif order_type == 'limit':
                price = float(order_data['price'])
                result = session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=side,
                    orderType="Limit",
                    qty=qty,
                    price=price,
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            return {
                'order_id': result['result']['orderId'],
                'symbol': result['result']['symbol'],
                'status': result['result']['orderStatus'],
                'executed_qty': result['result'].get('qty', '0'),
                'price': result['result'].get('avgPrice', result['result'].get('price')),
                'side': result['result']['side'],
                'type': result['result']['orderType'],
                'transact_time': result['result']['createdTime'],
            }

        except Exception as e:
            logger.error(f"Bybit execution failed: {e}")
            raise


# Placeholder for OKX, MEXC, Alpaca
class OKXExecutor(BaseExecutor):
    @staticmethod
    def execute(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        raise NotImplementedError("OKX executor not implemented yet")


class MEXCExecutor(BaseExecutor):
    @staticmethod
    def execute(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        raise NotImplementedError("MEXC executor not implemented yet")


class AlpacaExecutor(BaseExecutor):
    @staticmethod
    def execute(order_data: Dict[str, Any], credentials: ExchangeCredentials) -> Dict[str, Any]:
        raise NotImplementedError("Alpaca executor not implemented yet")