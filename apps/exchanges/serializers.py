"""
Serializers for exchange integration models.
"""

from rest_framework import serializers

from apps.payments.models import BlockchainAddress


class BlockchainAddressSerializer(serializers.ModelSerializer):
    """
    Serializer for BlockchainAddress model.
    """

    class Meta:
        model = BlockchainAddress
        fields = [
            "id",
            "coin_type",
            "blockchain",
            "address",
            "label",
            "is_active",
            "is_hot_wallet",
            "balance",
            "last_used",
            "usage_count",
            "requires_multisig",
            "min_confirmations",
            "max_daily_limit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "balance", "last_used", "usage_count", "created_at", "updated_at"]
