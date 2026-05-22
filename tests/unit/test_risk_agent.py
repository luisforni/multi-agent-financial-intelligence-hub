from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config import Settings
from shared.models import (
    InvestmentRecommendation,
    RiskLevel,
    SentimentData,
    Signal,
    StockData,
)

from risk_agent.agent import RiskAgent
from risk_agent.scorers.portfolio import PortfolioAnalyzer
from risk_agent.scorers.risk_scorer import RiskScorer


class TestPortfolioAnalyzer:
    def test_kelly_criterion_positive_edge(self) -> None:
        kelly = PortfolioAnalyzer.kelly_criterion(win_probability=0.6, win_loss_ratio=1.5)
        assert 0.0 < kelly <= 0.25

    def test_kelly_criterion_no_edge(self) -> None:
        kelly = PortfolioAnalyzer.kelly_criterion(win_probability=0.4, win_loss_ratio=1.0)
        assert kelly == 0.0

    def test_kelly_criterion_capped_at_25_percent(self) -> None:
        kelly = PortfolioAnalyzer.kelly_criterion(win_probability=0.99, win_loss_ratio=10.0)
        assert kelly == 0.25

    def test_position_size_from_atr(self) -> None:
        result = PortfolioAnalyzer.position_size_from_atr(
            portfolio_value=100_000,
            atr=3.20,
            current_price=195.50,
            risk_pct=0.01,
        )
        assert result["shares"] > 0
        assert result["notional"] > 0
        assert result["stop_loss"] < 195.50

    def test_price_targets_bullish(self) -> None:
        targets = PortfolioAnalyzer.compute_price_targets(
            current_price=100.0, atr=2.0, signal_direction="bullish"
        )
        assert targets["target_bull"] > targets["target_base"] > targets["target_bear"]
        assert targets["stop_loss"] < 100.0

    def test_price_targets_bearish(self) -> None:
        targets = PortfolioAnalyzer.compute_price_targets(
            current_price=100.0, atr=2.0, signal_direction="bearish"
        )
        assert targets["target_bear"] < targets["target_base"] < targets["target_bull"]
        assert targets["stop_loss"] > 100.0


class TestRiskScorer:
    def test_risk_level_classification_very_high(self) -> None:
        metrics = RiskAgent._build_risk_metrics("TEST", {"historical_volatility_30d": 0.85})
        assert metrics.risk_level == RiskLevel.VERY_HIGH

    def test_risk_level_classification_low(self) -> None:
        metrics = RiskAgent._build_risk_metrics("TEST", {"historical_volatility_30d": 0.12})
        assert metrics.risk_level == RiskLevel.LOW

    def test_risk_level_classification_moderate(self) -> None:
        metrics = RiskAgent._build_risk_metrics("TEST", {"historical_volatility_30d": 0.30})
        assert metrics.risk_level == RiskLevel.MODERATE


class TestRiskAgent:
    @pytest.fixture
    def agent(self, mock_settings: Settings) -> RiskAgent:
        return RiskAgent(mock_settings)

    @pytest.mark.asyncio
    async def test_analyze_returns_recommendation(
        self,
        agent: RiskAgent,
        sample_stock_data: StockData,
        sample_sentiment_data: SentimentData,
    ) -> None:
        risk_metrics_raw = {
            "historical_volatility_30d": 0.22,
            "historical_volatility_90d": 0.24,
            "value_at_risk_95": 0.0185,
            "sharpe_ratio": 1.45,
            "sortino_ratio": 2.10,
            "max_drawdown": -0.185,
            "beta": 1.18,
        }

        with patch.object(agent._risk_scorer, "compute", return_value=risk_metrics_raw):
            submit_input = {
                "signal": "BUY",
                "confidence": 0.72,
                "risk_level": "MODERATE",
                "time_horizon_days": 60,
                "target_price_bull": 220.0,
                "target_price_base": 210.0,
                "target_price_bear": 185.0,
                "stop_loss": 188.0,
                "technical_score": 68.0,
                "fundamental_score": 72.0,
                "sentiment_score": 65.0,
                "risk_adjusted_score": 69.0,
                "executive_summary": "Strong BUY based on momentum and fundamentals.",
                "bull_case": "iPhone cycle + Services growth.",
                "bear_case": "China risk materializes.",
                "key_risks": ["China exposure", "Valuation"],
                "key_catalysts": ["Earnings", "WWDC"],
            }

            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "submit_recommendation"
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

            result = await agent.analyze(sample_stock_data, sample_sentiment_data)

            assert isinstance(result, InvestmentRecommendation)
            assert result.signal == Signal.BUY
            assert result.confidence == 0.72
            assert result.risk_level == RiskLevel.MODERATE
            assert len(result.agents_used) == 3

    @pytest.mark.asyncio
    async def test_invalid_signal_defaults_to_hold(
        self,
        agent: RiskAgent,
        sample_stock_data: StockData,
        sample_sentiment_data: SentimentData,
    ) -> None:
        with patch.object(agent._risk_scorer, "compute", return_value={}):
            mock_block = MagicMock()
            mock_block.type = "tool_use"
            mock_block.name = "submit_recommendation"
            mock_block.id = "tool_1"
            mock_block.input = {
                "signal": "INVALID",
                "confidence": 0.5,
                "risk_level": "MODERATE",
                "executive_summary": "Test",
                "bull_case": "Test",
                "bear_case": "Test",
                "key_risks": [],
                "key_catalysts": [],
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

            result = await agent.analyze(sample_stock_data, sample_sentiment_data)
            assert result.signal == Signal.HOLD
