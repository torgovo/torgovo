from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_throttle_cache(db):
    """Throttles use the default cache; clear between tests so per-IP
    counters don't bleed across the suite (causing spurious 429s)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client(db):
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def second_user(db):
    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="testpass123",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpass123",
    )


@pytest.fixture
def auth_client(api_client, user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def second_auth_client(api_client, second_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=second_user)
    return client


@pytest.fixture
def admin_client(api_client, admin_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def user_token(user):
    from rest_framework_simplejwt.tokens import AccessToken

    return str(AccessToken.for_user(user))


@pytest.fixture
def admin_token(admin_user):
    from rest_framework_simplejwt.tokens import AccessToken

    return str(AccessToken.for_user(admin_user))


# ==================== BOT SUBSCRIPTION FIXTURES ====================


@pytest.fixture
def bot_subscription_plan(db):
    from apps.payments.models import BotSubscriptionPlan

    return BotSubscriptionPlan.objects.create(
        bot_type="grid",
        name="Grid Bot Plan",
        price=Decimal("49.99"),
        duration_days=30,
    )


@pytest.fixture
def signal_bot_plan(db):
    from apps.payments.models import BotSubscriptionPlan

    return BotSubscriptionPlan.objects.create(
        bot_type="custom",
        name="Signal Bot Plan",
        price=Decimal("29.99"),
        duration_days=30,
    )


@pytest.fixture
def martingale_bot_plan(db):
    from apps.payments.models import BotSubscriptionPlan

    return BotSubscriptionPlan.objects.create(
        bot_type="martingale",
        name="Martingale Bot Plan",
        price=Decimal("59.99"),
        duration_days=30,
    )


@pytest.fixture
def quantum_ai_plan(db):
    from apps.payments.models import BotSubscriptionPlan

    return BotSubscriptionPlan.objects.create(
        bot_type="quantum_ai",
        name="Quantum AI Plan",
        price=Decimal("99.99"),
        duration_days=30,
    )


@pytest.fixture
def bot_subscription(db, user, bot_subscription_plan):
    from apps.payments.models import BotSubscription

    return BotSubscription.objects.create(
        user=user,
        plan=bot_subscription_plan,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


@pytest.fixture
def signal_bot_subscription(db, user, signal_bot_plan):
    from apps.payments.models import BotSubscription

    return BotSubscription.objects.create(
        user=user,
        plan=signal_bot_plan,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


@pytest.fixture
def martingale_bot_subscription(db, user, martingale_bot_plan):
    from apps.payments.models import BotSubscription

    return BotSubscription.objects.create(
        user=user,
        plan=martingale_bot_plan,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


@pytest.fixture
def quantum_ai_subscription(db, user, quantum_ai_plan):
    from apps.payments.models import BotSubscription

    return BotSubscription.objects.create(
        user=user,
        plan=quantum_ai_plan,
        status="active",
        expires_at=timezone.now() + timedelta(days=30),
    )


# ==================== QUANTUM AI FIXTURES ====================


@pytest.fixture
def quantum_fund(db):
    from apps.bots.models import QuantumAIFund

    return QuantumAIFund.objects.create(
        name="Master Fund",
        master_api_key="encrypted_key_here",
        master_secret_key="encrypted_secret_here",
        total_fund_value=Decimal("100000"),
        total_profit=Decimal("10000"),
        total_deposits=Decimal("50000"),
        monthly_min_return=Decimal("2.00"),
        monthly_max_return=Decimal("15.00"),
        reserve_buffer_pct=Decimal("10.00"),
    )


@pytest.fixture
def quantum_fund_without_deposits(db):
    from apps.bots.models import QuantumAIFund

    return QuantumAIFund.objects.create(
        name="Empty Fund",
        master_api_key="key",
        master_secret_key="secret",
        total_deposits=Decimal("0"),
    )


@pytest.fixture
def quantum_wallet(db):
    from apps.bots.models import QuantumDepositWallet

    return QuantumDepositWallet.objects.create(
        coin="USDT",
        blockchain="ERC20",
        address="0x1234567890abcdef1234567890abcdef12345678",
    )


# ==================== TELEGRAM FIXTURES ====================


@pytest.fixture
def telegram_plan(db):
    from apps.subscriptions.models import TelegramSignalPlan

    return TelegramSignalPlan.objects.create(
        name="Basic Plan",
        description="Basic signals",
        duration_days=30,
        price_usd=Decimal("49.99"),
    )


# ==================== TRADING FIXTURES ====================


@pytest.fixture
def exchange(db):
    from apps.exchanges.models import Exchange

    return Exchange.objects.create(
        name="binance",
        display_name="Binance",
        is_active=True,
        supports_testnet=True,
        supported_features=["spot", "futures"],
    )


@pytest.fixture
def trading_pair(db):
    from apps.exchanges.models import TradingPair

    return TradingPair.objects.create(
        exchange_name="binance",
        symbol="BTC/USDT",
        base_asset="BTC",
        quote_asset="USDT",
        is_active=True,
    )


@pytest.fixture
def exchange_status(db):
    from apps.investments.models import ExchangeStatus

    return ExchangeStatus.objects.create(
        exchange_name="binance",
        status="online",
        response_time_ms=120,
    )


@pytest.fixture
def supported_blockchain(db):
    from apps.investments.models import SupportedBlockchain

    return SupportedBlockchain.objects.create(
        name="Ethereum",
        blockchain_code="ERC20",
        native_coin="ETH",
    )


@pytest.fixture
def exchange_rate(db):
    from apps.investments.models import ExchangeRate

    return ExchangeRate.objects.create(
        from_currency="BTC",
        to_currency="USDT",
        rate=Decimal("45000.00"),
    )


@pytest.fixture
def strategy_config(db):
    from apps.trading.models import StrategyConfig

    return StrategyConfig.objects.create(
        name="Grid Conservative",
        strategy="grid",
        default_parameters={"max_levels": 10, "spacing": 1.0},
        is_active=True,
    )


@pytest.fixture
def valid_fernet_key():
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


@pytest.fixture
def exchange_credentials(db, user, valid_fernet_key):
    from django.test.utils import override_settings

    from apps.exchanges.models import ExchangeCredentials

    with override_settings(FERNET_KEY=valid_fernet_key):
        return ExchangeCredentials.objects.create(
            user=user,
            exchange_name="binance",
            api_key="test-api-key",
            secret_key="test-secret-key",
            is_active=True,
            is_testnet=True,
        )


# ==================== SIGNAL BOT FIXTURES ====================


@pytest.fixture
def signal_bot(db, user):
    from apps.bots.models import SignalBot

    return SignalBot.objects.create(
        user=user,
        bot_name="Test Signal Bot",
        exchange_name="binance",
        trading_pair="BTC/USDT",
        default_amount=Decimal("10"),
        is_active=True,
    )
