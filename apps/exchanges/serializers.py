"""
Serializers for exchange integration models
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from cryptography.fernet import Fernet

from .models import (
    ExchangeCredentials, TradingPair, ExchangeStatus,
    BlockchainAddress, Exchange
)

User = get_user_model()


class ExchangeSerializer(serializers.ModelSerializer):
    """
    Serializer for Exchange model.
    """
    class Meta:
        model = Exchange
        fields = [
            'id', 'name', 'display_name', 'api_base_url',
            'websocket_url', 'is_active', 'supports_testnet',
            'supported_features', 'rate_limit_per_minute', 'fee_rates'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExchangeCredentialsSerializer(serializers.ModelSerializer):
    """
    Serializer for ExchangeCredentials model with encrypted API key handling.
    """
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    exchange_display_name = serializers.CharField(source='exchange.display_name', read_only=True)

    # Hide sensitive information in responses
    api_key = serializers.CharField(write_only=True)
    api_secret = serializers.CharField(write_only=True)
    passphrase = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Display masked versions
    masked_api_key = serializers.SerializerMethodField()

    class Meta:
        model = ExchangeCredentials
        fields = [
            'id', 'exchange', 'exchange_name', 'exchange_display_name',
            'api_key', 'api_secret', 'passphrase', 'masked_api_key',
            'testnet', 'is_active', 'created_at', 'updated_at',
            'last_verified', 'verification_status'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at',
            'last_verified', 'verification_status'
        ]
        extra_kwargs = {
            'exchange': {'required': True},
            'testnet': {'default': False},
            'is_active': {'default': True}
        }

    def get_masked_api_key(self, obj):
        """Return masked API key for display."""
        if obj.api_key:
            # Show first 4 and last 4 characters
            key = obj.api_key
            if len(key) > 8:
                return f"{key[:4]}...{key[-4:]}"
        return "****"

    def validate_exchange(self, value):
        """Validate that exchange is active."""
        if not value.is_active:
            raise serializers.ValidationError("This exchange is currently not available")
        return value

    def create(self, validated_data):
        """Create exchange credentials with encrypted API keys."""
        user = self.context['request'].user

        # Check if user already has credentials for this exchange
        existing = ExchangeCredentials.objects.filter(
            user=user, exchange=validated_data['exchange']
        ).first()

        if existing:
            raise serializers.ValidationError(
                f"You already have credentials configured for {validated_data['exchange'].display_name}"
            )

        # Encrypt sensitive data
        api_key = validated_data.pop('api_key')
        api_secret = validated_data.pop('api_secret')
        passphrase = validated_data.pop('passphrase', None)

        # Create credentials
        credentials = ExchangeCredentials.objects.create(
            user=user,
            **validated_data
        )

        # Set encrypted fields
        credentials.set_api_key(api_key)
        credentials.set_api_secret(api_secret)
        if passphrase:
            credentials.set_passphrase(passphrase)

        credentials.save()
        return credentials

    def update(self, instance, validated_data):
        """Update exchange credentials with encryption."""
        # Handle encrypted fields
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        passphrase = validated_data.pop('passphrase', None)

        # Update instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update encrypted fields if provided
        if api_key:
            instance.set_api_key(api_key)
        if api_secret:
            instance.set_api_secret(api_secret)
        if passphrase is not None:  # Allow empty string
            instance.set_passphrase(passphrase)

        instance.save()
        return instance


class TradingPairSerializer(serializers.ModelSerializer):
    """
    Serializer for TradingPair model.
    """
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    exchange_display_name = serializers.CharField(source='exchange.display_name', read_only=True)

    class Meta:
        model = TradingPair
        fields = [
            'id', 'exchange', 'exchange_name', 'exchange_display_name',
            'symbol', 'base_asset', 'quote_asset', 'is_active',
            'min_order_size', 'max_order_size', 'price_precision',
            'quantity_precision', 'maker_fee', 'taker_fee',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at'
        ]

    def validate_symbol(self, value):
        """Validate trading pair symbol format."""
        if '/' not in value:
            raise serializers.ValidationError("Symbol must be in format BASE/QUOTE")
        return value.upper()


class ExchangeStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for ExchangeStatus model.
    """
    exchange_name = serializers.CharField(source='exchange.name', read_only=True)
    exchange_display_name = serializers.CharField(source='exchange.display_name', read_only=True)

    class Meta:
        model = ExchangeStatus
        fields = [
            'id', 'exchange', 'exchange_name', 'exchange_display_name',
            'status', 'message', 'last_checked', 'response_time_ms',
            'is_trading_enabled', 'api_version', 'maintenance_mode',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at'
        ]


class BlockchainAddressSerializer(serializers.ModelSerializer):
    """
    Serializer for BlockchainAddress model with encryption.
    """
    address = serializers.CharField(write_only=True)
    masked_address = serializers.SerializerMethodField()

    class Meta:
        model = BlockchainAddress
        fields = [
            'id', 'cryptocurrency', 'address', 'masked_address',
            'label', 'is_default', 'is_active', 'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'cryptocurrency': {'required': True},
            'is_default': {'default': False},
            'is_active': {'default': True}
        }

    def get_masked_address(self, obj):
        """Return masked address for display."""
        if obj.address:
            # Show first 6 and last 4 characters
            addr = obj.address
            if len(addr) > 10:
                return f"{addr[:6]}...{addr[-4:]}"
        return "****"

    def validate_cryptocurrency(self, value):
        """Validate cryptocurrency code."""
        value = value.upper()
        # Basic validation for common cryptocurrency codes
        if len(value) < 2 or len(value) > 10:
            raise serializers.ValidationError("Invalid cryptocurrency code")
        return value

    def create(self, validated_data):
        """Create blockchain address with encryption."""
        user = self.context['request'].user

        # Check for duplicate addresses
        address = validated_data['address']
        cryptocurrency = validated_data['cryptocurrency']

        if BlockchainAddress.objects.filter(
            user=user,
            cryptocurrency=cryptocurrency,
            address=address
        ).exists():
            raise serializers.ValidationError("This address is already saved")

        # Handle default setting
        if validated_data.get('is_default', False):
            # Unset other default addresses for this cryptocurrency
            BlockchainAddress.objects.filter(
                user=user,
                cryptocurrency=cryptocurrency
            ).update(is_default=False)

        # Encrypt address
        address_data = validated_data.pop('address')

        blockchain_address = BlockchainAddress.objects.create(
            user=user,
            **validated_data
        )

        blockchain_address.set_address(address_data)
        blockchain_address.save()

        return blockchain_address

    def update(self, instance, validated_data):
        """Update blockchain address."""
        address = validated_data.pop('address', None)

        # Handle default setting
        if validated_data.get('is_default', False):
            # Unset other default addresses for this cryptocurrency
            BlockchainAddress.objects.filter(
                user=instance.user,
                cryptocurrency=instance.cryptocurrency
            ).exclude(id=instance.id).update(is_default=False)

        # Update instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update address if provided
        if address:
            instance.set_address(address)

        instance.save()
        return instance


class ExchangeListSerializer(serializers.ModelSerializer):
    """
    Simple serializer for exchange list endpoint.
    """
    class Meta:
        model = Exchange
        fields = [
            'name', 'display_name', 'is_active', 'supports_testnet',
            'supported_features', 'fee_rates'
        ]


class ExchangeRateSerializer(serializers.Serializer):
    """
    Serializer for exchange rate responses.
    """
    symbol = serializers.CharField()
    price = serializers.DecimalField(max_digits=20, decimal_places=8)
    exchange = serializers.CharField()
    volume_24h = serializers.DecimalField(max_digits=20, decimal_places=8)
    change_24h = serializers.DecimalField(max_digits=10, decimal_places=4)