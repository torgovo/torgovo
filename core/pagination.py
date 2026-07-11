"""
Custom pagination for Torgovo Crypto Trading Platform
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for API endpoints.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


class LargeResultsSetPagination(PageNumberPagination):
    """
    Large pagination for endpoints with more data.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


class SmallResultsSetPagination(PageNumberPagination):
    """
    Small pagination for endpoints with limited data.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


class TradeHistoryPagination(PageNumberPagination):
    """
    Special pagination for trade history with enhanced metadata.
    """
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        # Calculate additional metadata for trade history
        total_volume = sum(
            float(trade.get('Quantity', 0)) * float(trade.get('Price', 0))
            for trade in data
            if trade.get('Quantity') and trade.get('Price')
        )

        total_trades = len(data)
        winning_trades = len([
            trade for trade in data
            if trade.get('Details', {}).get('profit_loss', 0) > 0
        ])

        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
            'metadata': {
                'total_volume': round(total_volume, 2),
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0,
            }
        })


class BotListPagination(PageNumberPagination):
    """
    Pagination for bot lists with status summary.
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        # Count bots by status
        running_bots = len([bot for bot in data if bot.get('is_running', False)])
        total_bots = len(data)

        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
            'summary': {
                'total_bots': total_bots,
                'running_bots': running_bots,
                'stopped_bots': total_bots - running_bots,
            }
        })