"""
Telegram notification service for sending messages and trade alerts
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger('apps')

class TelegramService:
    """Service for sending Telegram notifications."""
    
    @staticmethod
    def send_message(token, chat_id, message):
        """
        Send a message to a Telegram chat.
        
        Args:
            token: Telegram bot token
            chat_id: Telegram chat ID
            message: Message text to send
            
        Returns:
            bool: Success status
        """
        if not token or not chat_id:
            logger.warning("Telegram token or chat_id missing, skipping notification")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'  # Enable markdown formatting
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Telegram message sent successfully to chat {chat_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {str(e)}")
            return False
    
    @staticmethod
    def send_trade_alert(user, trade_data):
        """
        Format and send a trade notification to user's Telegram.
        
        Args:
            user: Django user instance with telegram_token and telegram_chat_id
            trade_data: Dictionary with trade details (symbol, side, amount, price, exchange)
        """
        if not hasattr(user, 'telegram_token') or not hasattr(user, 'telegram_chat_id'):
            logger.info(f"User {user.id} has no Telegram configuration")
            return False
        
        if not user.telegram_token or not user.telegram_chat_id:
            return False
        
        # Format the message
        message = TelegramService.format_trade_message(trade_data)
        
        return TelegramService.send_message(
            user.telegram_token,
            user.telegram_chat_id,
            message
        )
    
    @staticmethod
    def format_trade_message(trade_data):
        """Format trade data into a readable message."""
        symbol = trade_data.get('symbol', 'N/A')
        side = trade_data.get('side', 'N/A').upper()
        amount = trade_data.get('amount', '0')
        price = trade_data.get('price', '0')
        exchange = trade_data.get('exchange', 'N/A')
        pnl = trade_data.get('pnl', None)
        
        emoji = "🟢" if side == "BUY" else "🔴"
        
        message = f"""{emoji} **Trade Executed**

**Symbol:** {symbol}
**Type:** {side}
**Amount:** {amount}
**Price:** {price}
**Exchange:** {exchange}
"""
        
        if pnl is not None:
            pnl_emoji = "📈" if float(pnl) > 0 else "📉"
            message += f"**P&L:** {pnl_emoji} {pnl}\n"
        
        message += f"**Time:** {trade_data.get('timestamp', '')}"
        
        return message
    
    @staticmethod
    def send_admin_alert(message):
        """
        Send an alert to the admin Telegram chat.
        Uses ADMIN_TELEGRAM_TOKEN and ADMIN_TELEGRAM_CHAT_ID from settings.
        """
        token = getattr(settings, 'ADMIN_TELEGRAM_TOKEN', None)
        chat_id = getattr(settings, 'ADMIN_TELEGRAM_CHAT_ID', None)
        if not token or not chat_id:
            logger.warning("Admin Telegram credentials not configured, skipping admin alert")
            return False
        return TelegramService.send_message(token, chat_id, message)

    @staticmethod
    def notify_bot_started(user, bot_type, bot_config):
        """Notify user that a bot has started."""
        if not user.telegram_token or not user.telegram_chat_id:
            return False
        
        message = f"""🤖 **Bot Started**

**Type:** {bot_type}
**Pair:** {bot_config.get('trading_pair', 'N/A')}
**Exchange:** {bot_config.get('exchange_name', 'N/A')}
"""
        
        return TelegramService.send_message(
            user.telegram_token,
            user.telegram_chat_id,
            message
        )
    
    @staticmethod
    def notify_bot_stopped(user, bot_type, reason="User stopped"):
        """Notify user that a bot has stopped."""
        if not user.telegram_token or not user.telegram_chat_id:
            return False
        
        message = f"""⏹️ **Bot Stopped**

**Type:** {bot_type}
**Reason:** {reason}
"""
        
        return TelegramService.send_message(
            user.telegram_token,
            user.telegram_chat_id,
            message
        )
