"""
Views for exchange integration endpoints.

Canonical exchange endpoints live in apps.trading.views and are re-exported
via apps/exchanges/urls.py for legacy namespace compatibility.

This module only contains BlockchainAddressViewSet, which is unique to the
exchanges app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.payments.models import BlockchainAddress

from .serializers import BlockchainAddressSerializer


class BlockchainAddressViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing blockchain addresses.

    Read: any authenticated user
    Write (create/update/delete): staff only
    """

    serializer_class = BlockchainAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BlockchainAddress.objects.filter(is_active=True)

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"])
    def cryptocurrency(self, request):
        """Get addresses for specific cryptocurrency."""
        crypto = request.query_params.get("crypto", None)
        if crypto:
            addresses = self.get_queryset().filter(coin_type=crypto.upper())
            serializer = self.get_serializer(addresses, many=True)
            return Response(serializer.data)
        return Response(
            {"error": "Cryptocurrency parameter required"}, status=status.HTTP_400_BAD_REQUEST
        )
