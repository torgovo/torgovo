"""
Serializers for trading models
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import (
    Exchange, ExchangeCredentials, TradingPair,
    ExchangeStatus, SupportedBlockchain, ExchangeRate,
    StrategyConfig
)

User = get_user_model()


class ExchangeSerializer(serializers.ModelSerializer):
    """Serializer for Exchange model."""
    class Meta:
        model = Exchange
        fields = [
            'id', 'name', 'display_name', 'api_base_url',
            'websocket_url', 'is_active', 'supports_testnet',
            'supported_features', 'rate_limit_per_minute', 'fee_rates',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExchangeCredentialsSerializer(serializers.ModelSerializer):
    """Serializer for ExchangeCredentials model with encrypted API key handling."""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    api_key_display = serializers.SerializerMethodField()
    secret_key_display = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeCredentials
        fields = [
            'id', 'user', 'user_email', 'exchange_name',
            'api_key_display', 'secret_key_display',
            'is_active', 'is_testnet', 'permissions',
            'last_verified', 'verification_status',
            'trading_enabled', 'withdrawal_enabled', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'user_email', 'api_key_display',
            'secret_key_display', 'last_verified', 'verification_status',
            'created_at', 'updated_at'
        ]

    def get_api_key_display(self, obj):
        """Return masked API key for display."""
        return "****" if obj.api_key else None

    def get_secret_key_display(self, obj):
        """Return masked secret key for display."""
        return "****" if obj.secret_key else None


class ExchangeCredentialsCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating ExchangeCredentials (accepts raw keys)."""
    class Meta:
        model = ExchangeCredentials
        fields = [
            'exchange_name', 'api_key', 'secret_key', 'passphrase',
            'is_testnet', 'permissions', 'notes'
        ]


class TradingPairSerializer(serializers.ModelSerializer):
    """Serializer for TradingPair model."""
    class Meta:
        model = TradingPair
        fields = [
            'id', 'exchange_name', 'symbol', 'base_asset', 'quote_asset',
            'is_active', 'min_order_size', 'max_order_size',
            'price_precision', 'quantity_precision', 'maker_fee',
            'taker_fee', 'min_notional', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExchangeStatusSerializer(serializers.ModelSerializer):
    """Serializer for ExchangeStatus model."""
    class Meta:
        model = ExchangeStatus
        fields = [
            'id', 'exchange_name', 'status', 'response_time_ms',
            'last_check', 'error_message', 'api_limits',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SupportedBlockchainSerializer(serializers.ModelSerializer):
    """Serializer for SupportedBlockchain model."""
    class Meta:
        model = SupportedBlockchain
        fields = [
            'id', 'name', 'blockchain_code', 'native_coin',
            'explorer_url', 'confirmation_blocks',
            'transaction_fee_type', 'average_fee', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExchangeRateSerializer(serializers.ModelSerializer):
    """Serializer for ExchangeRate model."""
    class Meta:
        model = ExchangeRate
        fields = [
            'id', 'from_currency', 'to_currency', 'rate',
            'exchange_name', 'source', 'timestamp',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'timestamp', 'created_at', 'updated_at']


class StrategyConfigSerializer(serializers.ModelSerializer):
    """Serializer for StrategyConfig (default presets per strategy type)."""
    strategy_display = serializers.CharField(source='get_strategy_display', read_only=True)

    class Meta:
        model = StrategyConfig
        fields = [
            'id', 'name', 'strategy', 'strategy_display',
            'default_parameters', 'description', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
