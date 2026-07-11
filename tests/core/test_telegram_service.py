from unittest.mock import patch, MagicMock

import pytest

from core.telegram_service import TelegramService


class TestTelegramServiceSendMessage:
    @patch("core.telegram_service.requests.post")
    def test_send_message_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = TelegramService.send_message(
            token="12345:ABC-DEF",
            chat_id="-100123456789",
            message="Hello, world!",
        )
        assert result is True
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bot12345:ABC-DEF/sendMessage",
            json={
                "chat_id": "-100123456789",
                "text": "Hello, world!",
                "parse_mode": "Markdown",
            },
            timeout=10,
        )

    @patch("core.telegram_service.requests.post")
    def test_send_message_empty_token(self, mock_post):
        result = TelegramService.send_message(
            token="",
            chat_id="-100123456789",
            message="Hello!",
        )
        assert result is False
        mock_post.assert_not_called()

    @patch("core.telegram_service.requests.post")
    def test_send_message_none_token(self, mock_post):
        result = TelegramService.send_message(
            token=None,
            chat_id="-100123456789",
            message="Hello!",
        )
        assert result is False
        mock_post.assert_not_called()

    @patch("core.telegram_service.requests.post")
    def test_send_message_empty_chat_id(self, mock_post):
        result = TelegramService.send_message(
            token="12345:ABC",
            chat_id="",
            message="Hello!",
        )
        assert result is False
        mock_post.assert_not_called()

    @patch("core.telegram_service.requests.post")
    def test_send_message_request_exception(self, mock_post):
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Connection error")

        result = TelegramService.send_message(
            token="12345:ABC",
            chat_id="-100123456789",
            message="Hello!",
        )
        assert result is False

    @patch("core.telegram_service.requests.post")
    def test_send_message_generic_exception(self, mock_post):
        mock_post.side_effect = Exception("Unexpected error")

        result = TelegramService.send_message(
            token="12345:ABC",
            chat_id="-100123456789",
            message="Hello!",
        )
        assert result is False

    @patch("core.telegram_service.requests.post")
    def test_send_message_http_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 403")
        mock_post.return_value = mock_response

        result = TelegramService.send_message(
            token="12345:ABC",
            chat_id="-100123456789",
            message="Hello!",
        )
        assert result is False


class TestTelegramServiceSendTradeAlert:
    def test_user_without_telegram_config(self):
        user = MagicMock()
        del user.telegram_token
        result = TelegramService.send_trade_alert(user, {})
        assert result is False

    def test_user_with_empty_token(self):
        user = MagicMock()
        user.telegram_token = ""
        user.telegram_chat_id = "-100123"
        result = TelegramService.send_trade_alert(user, {})
        assert result is False

    def test_user_with_empty_chat_id(self):
        user = MagicMock()
        user.telegram_token = "123:ABC"
        user.telegram_chat_id = ""
        result = TelegramService.send_trade_alert(user, {})
        assert result is False

    @patch.object(TelegramService, "send_message")
    def test_sends_formatted_message(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "12345:ABC"
        user.telegram_chat_id = "-100123456789"

        trade_data = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "amount": "0.5",
            "price": "50000",
            "exchange": "Binance",
            "pnl": 150.0,
            "timestamp": "2026-01-15 10:30:00",
        }
        result = TelegramService.send_trade_alert(user, trade_data)
        assert result is True
        mock_send_message.assert_called_once()
        args, kwargs = mock_send_message.call_args
        assert kwargs["token"] == "12345:ABC"
        assert kwargs["chat_id"] == "-100123456789"
        message = kwargs["message"]
        assert "BTC/USDT" in message
        assert "BUY" in message
        assert "0.5" in message
        assert "50000" in message
        assert "Binance" in message
        assert "150" in message

    @patch.object(TelegramService, "send_message")
    def test_sell_trade_alert(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        trade_data = {
            "symbol": "ETH/USDT",
            "side": "SELL",
            "amount": "1.0",
            "price": "3000",
            "exchange": "Bybit",
        }
        result = TelegramService.send_trade_alert(user, trade_data)
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "SELL" in message
        assert "ETH/USDT" in message
        assert "Bybit" in message

    @patch.object(TelegramService, "send_message")
    def test_trade_alert_without_pnl(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        trade_data = {
            "symbol": "SOL/USDT",
            "side": "BUY",
            "amount": "10",
            "price": "150",
            "exchange": "Binance",
        }
        result = TelegramService.send_trade_alert(user, trade_data)
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "P&L" not in message


class TestTelegramServiceFormatTradeMessage:
    def test_buy_trade_message(self):
        trade_data = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "amount": "0.5",
            "price": "50000",
            "exchange": "Binance",
        }
        message = TelegramService.format_trade_message(trade_data)
        assert "**Trade Executed**" in message
        assert "**Symbol:** BTC/USDT" in message
        assert "**Type:** BUY" in message
        assert "**Amount:** 0.5" in message
        assert "**Price:** 50000" in message
        assert "**Exchange:** Binance" in message

    def test_sell_trade_message(self):
        trade_data = {
            "symbol": "ETH/USDT",
            "side": "SELL",
            "amount": "1.0",
            "price": "3000",
            "exchange": "Bybit",
        }
        message = TelegramService.format_trade_message(trade_data)
        assert "**Type:** SELL" in message

    def test_trade_message_with_pnl(self):
        trade_data = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "amount": "0.5",
            "price": "50000",
            "exchange": "Binance",
            "pnl": "250.50",
        }
        message = TelegramService.format_trade_message(trade_data)
        assert "250.50" in message
        assert "P&L" in message

    def test_trade_message_with_negative_pnl(self):
        trade_data = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "amount": "0.5",
            "price": "50000",
            "exchange": "Binance",
            "pnl": "-100.00",
        }
        message = TelegramService.format_trade_message(trade_data)
        assert "-100.00" in message
        assert "P&L" in message

    def test_defaults_for_missing_fields(self):
        message = TelegramService.format_trade_message({})
        assert "**Symbol:** N/A" in message
        assert "**Type:** N/A" in message
        assert "**Amount:** 0" in message
        assert "**Price:** 0" in message
        assert "**Exchange:** N/A" in message

    def test_includes_timestamp(self):
        trade_data = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "amount": "0.5",
            "price": "50000",
            "exchange": "Binance",
            "timestamp": "2026-06-14 12:00:00",
        }
        message = TelegramService.format_trade_message(trade_data)
        assert "**Time:** 2026-06-14 12:00:00" in message


class TestTelegramServiceNotifyBotStarted:
    @patch.object(TelegramService, "send_message")
    def test_notify_bot_started_success(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_started(
            user, "GridBot", {"trading_pair": "BTC/USDT", "exchange_name": "Binance"}
        )
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "**Bot Started**" in message
        assert "**Type:** GridBot" in message
        assert "**Pair:** BTC/USDT" in message
        assert "**Exchange:** Binance" in message

    @patch.object(TelegramService, "send_message")
    def test_notify_bot_started_no_telegram(self, mock_send_message):
        user = MagicMock()
        user.telegram_token = ""
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_started(user, "GridBot", {})
        assert result is False
        mock_send_message.assert_not_called()

    @patch.object(TelegramService, "send_message")
    def test_notify_bot_started_default_pair_exchange(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_started(user, "DCA", {})
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "**Pair:** N/A" in message
        assert "**Exchange:** N/A" in message


class TestTelegramServiceNotifyBotStopped:
    @patch.object(TelegramService, "send_message")
    def test_notify_bot_stopped_success(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_stopped(user, "GridBot", "TP hit")
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "**Bot Stopped**" in message
        assert "**Type:** GridBot" in message
        assert "**Reason:** TP hit" in message

    @patch.object(TelegramService, "send_message")
    def test_notify_bot_stopped_default_reason(self, mock_send_message):
        mock_send_message.return_value = True
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_stopped(user, "Martingale")
        assert result is True
        message = mock_send_message.call_args[1]["message"]
        assert "User stopped" in message

    @patch.object(TelegramService, "send_message")
    def test_notify_bot_stopped_no_telegram(self, mock_send_message):
        user = MagicMock()
        user.telegram_token = None
        user.telegram_chat_id = "123"

        result = TelegramService.notify_bot_stopped(user, "Bot")
        assert result is False
        mock_send_message.assert_not_called()

    @patch.object(TelegramService, "send_message")
    def test_notify_bot_stopped_no_chat_id(self, mock_send_message):
        user = MagicMock()
        user.telegram_token = "tok"
        user.telegram_chat_id = None

        result = TelegramService.notify_bot_stopped(user, "Bot")
        assert result is False
        mock_send_message.assert_not_called()
