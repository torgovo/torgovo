from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIRequestFactory

from core.pagination import (
    BotListPagination,
    LargeResultsSetPagination,
    SmallResultsSetPagination,
    StandardResultsSetPagination,
    TradeHistoryPagination,
)

factory = APIRequestFactory()


def build_paginated_instance(pagination_cls, data, count=100):
    paginator = pagination_cls()
    paginator.page = MagicMock()
    paginator.page.paginator.count = count
    paginator.get_next_link = MagicMock(return_value="http://example.com/?page=2")
    paginator.get_previous_link = MagicMock(return_value=None)
    return paginator.get_paginated_response(data)


class TestStandardResultsSetPagination:
    def test_default_page_size(self):
        assert StandardResultsSetPagination.page_size == 20

    def test_max_page_size(self):
        assert StandardResultsSetPagination.max_page_size == 100

    def test_page_size_query_param(self):
        assert StandardResultsSetPagination.page_size_query_param == "page_size"

    def test_paginated_response_structure(self):
        data = [{"id": i} for i in range(20)]
        response = build_paginated_instance(StandardResultsSetPagination, data, count=100)
        assert response.data["count"] == 100
        assert response.data["next"] == "http://example.com/?page=2"
        assert response.data["previous"] is None
        assert response.data["results"] == data

    def test_paginated_response_keys(self):
        data = [{"id": 1}]
        response = build_paginated_instance(StandardResultsSetPagination, data, count=1)
        assert set(response.data.keys()) == {"count", "next", "previous", "results"}


class TestLargeResultsSetPagination:
    def test_default_page_size(self):
        assert LargeResultsSetPagination.page_size == 50

    def test_max_page_size(self):
        assert LargeResultsSetPagination.max_page_size == 200

    def test_paginated_response_structure(self):
        data = [{"id": i} for i in range(50)]
        response = build_paginated_instance(LargeResultsSetPagination, data, count=200)
        assert response.data["count"] == 200
        assert len(response.data["results"]) == 50

    def test_paginated_response_keys(self):
        data = [{"id": 1}]
        response = build_paginated_instance(LargeResultsSetPagination, data, count=1)
        assert set(response.data.keys()) == {"count", "next", "previous", "results"}


class TestSmallResultsSetPagination:
    def test_default_page_size(self):
        assert SmallResultsSetPagination.page_size == 10

    def test_max_page_size(self):
        assert SmallResultsSetPagination.max_page_size == 50

    def test_paginated_response_structure(self):
        data = [{"id": i} for i in range(10)]
        response = build_paginated_instance(SmallResultsSetPagination, data, count=30)
        assert response.data["count"] == 30
        assert len(response.data["results"]) == 10

    def test_paginated_response_keys(self):
        data = [{"id": 1}]
        response = build_paginated_instance(SmallResultsSetPagination, data, count=1)
        assert set(response.data.keys()) == {"count", "next", "previous", "results"}


class TestTradeHistoryPagination:
    def test_default_page_size(self):
        assert TradeHistoryPagination.page_size == 30

    def test_max_page_size(self):
        assert TradeHistoryPagination.max_page_size == 100

    def test_paginated_response_with_trades(self):
        data = [
            {"Quantity": "1.5", "Price": "100", "Details": {"profit_loss": 50}},
            {"Quantity": "2.0", "Price": "200", "Details": {"profit_loss": -20}},
            {"Quantity": "0.5", "Price": "50", "Details": {"profit_loss": 10}},
        ]
        response = build_paginated_instance(TradeHistoryPagination, data, count=3)
        assert response.data["count"] == 3
        assert response.data["results"] == data
        assert "metadata" in response.data
        meta = response.data["metadata"]
        assert meta["total_volume"] == pytest.approx(1.5 * 100 + 2.0 * 200 + 0.5 * 50)
        assert meta["total_trades"] == 3
        assert meta["winning_trades"] == 2
        assert meta["win_rate"] == pytest.approx(66.67, rel=0.01)

    def test_empty_trades(self):
        response = build_paginated_instance(TradeHistoryPagination, [], count=0)
        assert response.data["count"] == 0
        meta = response.data["metadata"]
        assert meta["total_volume"] == 0.0
        assert meta["total_trades"] == 0
        assert meta["winning_trades"] == 0
        assert meta["win_rate"] == 0

    def test_trades_without_quantity_price(self):
        data = [{"Details": {"profit_loss": 100}}]
        response = build_paginated_instance(TradeHistoryPagination, data, count=1)
        meta = response.data["metadata"]
        assert meta["total_volume"] == 0.0

    def test_response_keys(self):
        data = [{"Quantity": "1", "Price": "100", "Details": {"profit_loss": 10}}]
        response = build_paginated_instance(TradeHistoryPagination, data, count=1)
        assert set(response.data.keys()) == {"count", "next", "previous", "results", "metadata"}


class TestBotListPagination:
    def test_default_page_size(self):
        assert BotListPagination.page_size == 25

    def test_max_page_size(self):
        assert BotListPagination.max_page_size == 100

    def test_paginated_response(self):
        data = [
            {"name": "Bot 1", "is_running": True},
            {"name": "Bot 2", "is_running": False},
            {"name": "Bot 3", "is_running": True},
            {"name": "Bot 4", "is_running": False},
        ]
        response = build_paginated_instance(BotListPagination, data, count=4)
        assert response.data["count"] == 4
        assert response.data["results"] == data
        assert "summary" in response.data
        summary = response.data["summary"]
        assert summary["total_bots"] == 4
        assert summary["running_bots"] == 2
        assert summary["stopped_bots"] == 2

    def test_all_running_bots(self):
        data = [{"name": "Bot", "is_running": True} for _ in range(5)]
        response = build_paginated_instance(BotListPagination, data, count=5)
        summary = response.data["summary"]
        assert summary["running_bots"] == 5
        assert summary["stopped_bots"] == 0

    def test_all_stopped_bots(self):
        data = [{"name": "Bot", "is_running": False} for _ in range(3)]
        response = build_paginated_instance(BotListPagination, data, count=3)
        summary = response.data["summary"]
        assert summary["running_bots"] == 0
        assert summary["stopped_bots"] == 3

    def test_empty_list(self):
        response = build_paginated_instance(BotListPagination, [], count=0)
        summary = response.data["summary"]
        assert summary["total_bots"] == 0
        assert summary["running_bots"] == 0
        assert summary["stopped_bots"] == 0

    def test_response_keys(self):
        data = [{"name": "Bot", "is_running": True}]
        response = build_paginated_instance(BotListPagination, data, count=1)
        assert set(response.data.keys()) == {"count", "next", "previous", "results", "summary"}
