from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config import Settings
from shared.models import SentimentData, SentimentLabel

from sentiment_agent.agent import SentimentAgent


class TestSentimentAgent:
    @pytest.fixture
    def agent(self, mock_settings: Settings) -> SentimentAgent:
        return SentimentAgent(mock_settings)

    @pytest.mark.asyncio
    async def test_analyze_returns_sentiment_data(self, agent: SentimentAgent) -> None:
        with (
            patch.object(agent._reddit, "search_ticker", return_value=[]),
            patch.object(agent._news, "search_news", return_value=[]),
            patch.object(agent, "_get_fear_greed_index", return_value={"score": 55, "rating": "Greed"}),
            patch.object(agent, "_get_analyst_ratings", return_value={"recommendation_key": "buy"}),
        ):
            submit_input = {
                "overall_score": 0.42,
                "label": "BULLISH",
                "reddit_score": 0.35,
                "news_score": 0.50,
                "total_mentions": 100,
                "bullish_themes": ["Strong earnings", "AI growth"],
                "bearish_themes": ["China risk"],
                "key_catalysts": ["Earnings next week"],
                "sentiment_summary": "Overall bullish with strong institutional coverage.",
            }

            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "submit_sentiment_analysis"
            mock_block.id = "tool_1"
            mock_block.input = submit_input

            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"
            mock_response.content = [mock_block]

            mock_response2 = MagicMock()
            mock_response2.stop_reason = "end_turn"
            mock_response2.content = []

            agent._client.messages.create = AsyncMock(  # type: ignore[method-assign]
                side_effect=[mock_response, mock_response2]
            )

            result = await agent.analyze("AAPL", "Apple Inc.")

            assert result.ticker == "AAPL"
            assert result.overall_score == 0.42
            assert result.label == SentimentLabel.BULLISH
            assert "Strong earnings" in result.bullish_themes

    @pytest.mark.asyncio
    async def test_invalid_label_defaults_to_neutral(self, agent: SentimentAgent) -> None:
        with (
            patch.object(agent._reddit, "search_ticker", return_value=[]),
            patch.object(agent._news, "search_news", return_value=[]),
            patch.object(agent, "_get_fear_greed_index", return_value={}),
            patch.object(agent, "_get_analyst_ratings", return_value={}),
        ):
            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "submit_sentiment_analysis"
            mock_block.id = "tool_1"
            mock_block.input = {
                "overall_score": 0.0,
                "label": "INVALID_LABEL",
                "bullish_themes": [],
                "bearish_themes": [],
                "sentiment_summary": "No data",
            }

            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"
            mock_response.content = [mock_block]

            mock_response2 = MagicMock()
            mock_response2.stop_reason = "end_turn"
            mock_response2.content = []

            agent._client.messages.create = AsyncMock(  # type: ignore[method-assign]
                side_effect=[mock_response, mock_response2]
            )

            result = await agent.analyze("AAPL", "Apple Inc.")
            assert result.label == SentimentLabel.NEUTRAL
