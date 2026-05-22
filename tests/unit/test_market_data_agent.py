from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config import Settings
from shared.models import StockData, Signal

from market_data_agent.agent import MarketDataAgent
from market_data_agent.tools import format_stock_data_for_tool


class TestFormatStockDataForTool:
    def test_returns_valid_json(self, sample_stock_data: StockData) -> None:
        result = format_stock_data_for_tool(sample_stock_data)
        parsed = json.loads(result)
        assert parsed["ticker"] == "AAPL"
        assert parsed["price"] == 195.50
        assert "technicals" in parsed
        assert "fundamentals" in parsed

    def test_technicals_included(self, sample_stock_data: StockData) -> None:
        parsed = json.loads(format_stock_data_for_tool(sample_stock_data))
        assert parsed["technicals"]["rsi_14"] == 58.4
        assert parsed["technicals"]["macd"] == 1.25

    def test_fundamentals_included(self, sample_stock_data: StockData) -> None:
        parsed = json.loads(format_stock_data_for_tool(sample_stock_data))
        assert parsed["fundamentals"]["pe_ratio"] == 28.5
        assert parsed["fundamentals"]["sector"] == "Technology"


class TestMarketDataAgent:
    @pytest.fixture
    def agent(self, mock_settings: Settings) -> MarketDataAgent:
        return MarketDataAgent(mock_settings)

    @pytest.mark.asyncio
    async def test_analyze_returns_stock_data(
        self, agent: MarketDataAgent, sample_stock_data: StockData
    ) -> None:
        with (
            patch.object(agent._yf_provider, "get_stock_data", return_value=sample_stock_data),
            patch.object(agent, "_get_options_flow", return_value={"put_call_ratio": 0.8}),
            patch.object(agent, "_get_market_context", return_value={"vix_level": 18.5}),
        ):
            # Mock Claude tool-use response that calls submit_market_analysis directly
            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "submit_market_analysis"
            mock_block.id = "tool_1"
            mock_block.input = {
                "technical_summary": "Bullish momentum",
                "fundamental_summary": "Strong fundamentals",
                "technical_score": 68.0,
                "fundamental_score": 72.0,
            }

            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"
            mock_response.content = [mock_block]
            mock_response.usage = MagicMock()
            mock_response.usage.model_dump.return_value = {"input_tokens": 100, "output_tokens": 50}

            mock_response2 = MagicMock()
            mock_response2.stop_reason = "end_turn"
            mock_response2.content = []

            agent._client.messages.create = AsyncMock(  # type: ignore[method-assign]
                side_effect=[mock_response, mock_response2]
            )

            result = await agent.analyze("AAPL")

            assert result.ticker == "AAPL"
            assert result.current_price == 195.50
            assert result.technical_summary == "Bullish momentum"

    @pytest.mark.asyncio
    async def test_ticker_normalized_to_uppercase(
        self, agent: MarketDataAgent, sample_stock_data: StockData
    ) -> None:
        with (
            patch.object(agent._yf_provider, "get_stock_data", return_value=sample_stock_data),
            patch.object(agent, "_get_options_flow", return_value={}),
            patch.object(agent, "_get_market_context", return_value={}),
        ):
            mock_response = MagicMock()
            mock_response.stop_reason = "end_turn"
            mock_response.content = []
            mock_response.usage = MagicMock()
            mock_response.usage.model_dump.return_value = {}

            agent._client.messages.create = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
            result = await agent.analyze("aapl")

            assert result.ticker == "AAPL"
