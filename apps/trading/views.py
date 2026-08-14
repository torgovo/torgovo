"""
Views for trading endpoints
"""

import logging

from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.investments.models import ExchangeRate, ExchangeStatus
from core.pagination import StandardResultsSetPagination

from .models import Exchange, ExchangeCredentials, StrategyConfig, TradingPair
from .serializers import (
    ExchangeCredentialsCreateSerializer,
    ExchangeCredentialsSerializer,
    ExchangeSerializer,
    ExchangeStatusSerializer,
    StrategyConfigSerializer,
    TradingPairSerializer,
)

logger = logging.getLogger("apps.trading")


# =============================================================================
# EXCHANGE VIEWSETS
# =============================================================================


class ExchangeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing supported exchanges."""

    serializer_class = ExchangeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    queryset = Exchange.objects.filter(is_active=True)


class ExchangeCredentialsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing exchange credentials."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return ExchangeCredentialsCreateSerializer
        return ExchangeCredentialsSerializer

    def get_queryset(self):
        return ExchangeCredentials.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get active exchange credentials."""
        active_credentials = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_credentials, many=True)
        return Response(serializer.data)


class TradingPairViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing available trading pairs."""

    serializer_class = TradingPairSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = TradingPair.objects.filter(is_active=True)
        exchange_name = self.request.query_params.get("exchange", None)
        if exchange_name:
            queryset = queryset.filter(exchange_name=exchange_name)
        return queryset

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular trading pairs."""
        popular_pairs = self.get_queryset()[:20]
        serializer = self.get_serializer(popular_pairs, many=True)
        return Response(serializer.data)


class ExchangeStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for exchange status information."""

    serializer_class = ExchangeStatusSerializer
    queryset = ExchangeStatus.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination


# =============================================================================
# BOT CONFIGURATION VIEWSETS
# =============================================================================


class StrategyConfigViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing strategy presets (read-only for users)."""

    serializer_class = StrategyConfigSerializer
    permission_classes = [IsAuthenticated]
    queryset = StrategyConfig.objects.filter(is_active=True)


# =============================================================================
# FUNCTION-BASED VIEWS
# =============================================================================


@swagger_auto_schema(
    method="get",
    responses={
        200: openapi.Response(
            description="List of supported exchanges",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING),
                        "display_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    },
                ),
            ),
        )
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_exchanges(request):
    """List all supported cryptocurrency exchanges."""
    try:
        exchanges = Exchange.objects.filter(is_active=True)
        exchange_data = []

        for exchange in exchanges:
            exchange_data.append(
                {
                    "name": exchange.name,
                    "display_name": exchange.display_name,
                    "is_active": exchange.is_active,
                    "supports_testnet": exchange.supports_testnet,
                    "supported_features": exchange.supported_features,
                    "fee_rates": exchange.fee_rates,
                }
            )

        return Response({"success": True, "data": exchange_data})

    except Exception as e:
        logger.error(f"Error listing exchanges: {str(e)}")
        return Response(
            {"success": False, "error": "Failed to retrieve exchanges"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_exchange_symbols(request, exchange_name):
    """Get trading symbols for a specific exchange."""
    try:
        pairs = TradingPair.objects.filter(exchange_name=exchange_name, is_active=True)
        symbols = [pair.symbol for pair in pairs]

        return Response({"success": True, "exchange": exchange_name, "symbols": symbols})

    except Exception as e:
        logger.error(f"Error getting exchange symbols for {exchange_name}: {str(e)}")
        return Response(
            {"success": False, "error": f"Failed to retrieve symbols for {exchange_name}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_exchange_rates(request):
    """Get current exchange rates for trading pairs via CCXT."""
    try:
        import ccxt

        pairs_param = request.GET.get("pairs", None)
        exchange_param = request.GET.get("exchange", "bybit")
        rates = {}

        if pairs_param:
            symbols = [s.strip().upper() for s in pairs_param.split(",")]
            trading_pairs = TradingPair.objects.filter(symbol__in=symbols, is_active=True)[:50]
        else:
            trading_pairs = TradingPair.objects.filter(is_active=True)[:50]

        # Try live prices via CCXT (no auth needed for public tickers)
        try:
            exchange_class = getattr(ccxt, exchange_param.lower(), None)
            if exchange_class:
                exchange = exchange_class({"enableRateLimit": True})
                exchange.load_markets()

                for pair in trading_pairs:
                    try:
                        ticker = exchange.fetch_ticker(pair.symbol)
                        rates[pair.symbol] = {
                            "price": str(ticker.get("last", 0)),
                            "exchange": pair.exchange_name,
                            "volume_24h": str(ticker.get("quoteVolume", 0)),
                            "change_24h": str(ticker.get("percentage", 0)),
                            "high_24h": str(ticker.get("high", 0)),
                            "low_24h": str(ticker.get("low", 0)),
                        }
                    except Exception:
                        # Pair not available on this exchange
                        rates[pair.symbol] = {
                            "price": None,
                            "exchange": pair.exchange_name,
                            "error": f"{pair.symbol} not available on {exchange_param}",
                        }
            else:
                raise ValueError(f"Exchange {exchange_param} not supported")

        except Exception as e:
            logger.warning(f"CCXT fetch failed, falling back to DB: {e}")
            # Fallback: use ExchangeRate model
            for pair in trading_pairs:
                try:
                    rate_obj = ExchangeRate.objects.filter(
                        from_currency=pair.base_asset, to_currency=pair.quote_asset
                    ).latest("timestamp")
                    rates[pair.symbol] = {
                        "price": str(rate_obj.rate),
                        "exchange": rate_obj.exchange_name,
                        "source": "cached",
                    }
                except ExchangeRate.DoesNotExist:
                    rates[pair.symbol] = {"price": None, "exchange": pair.exchange_name}

        return Response({"success": True, "rates": rates, "timestamp": timezone.now().isoformat()})

    except Exception as e:
        logger.error(f"Error getting exchange rates: {str(e)}")
        return Response(
            {"success": False, "error": "Failed to retrieve exchange rates"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
