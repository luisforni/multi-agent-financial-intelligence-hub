from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.config import Settings
from shared.models import (
    CompanyFundamentals,
    InvestmentRecommendation,
    RiskLevel,
    RiskMetrics,
    SentimentData,
    SentimentLabel,
    Signal,
    StockData,
    TechnicalIndicators,
)


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY="sk-ant-test-key",
        REDIS_URL="redis://localhost:6379",
        POSTGRES_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/fintelligence_test",
        MARKET_DATA_AGENT_MODEL="anthropic/claude-opus-4-7",
        SENTIMENT_AGENT_MODEL="anthropic/claude-opus-4-7",
        RISK_AGENT_MODEL="anthropic/claude-opus-4-7",
    )


@pytest.fixture
def sample_stock_data() -> StockData:
    return StockData(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        currency="USD",
        current_price=195.50,
        open_price=193.00,
        high_price=197.20,
        low_price=192.80,
        previous_close=193.50,
        price_change=2.00,
        price_change_pct=1.03,
        volume=75_000_000,
        average_volume=65_000_000,
        week_52_high=220.00,
        week_52_low=165.00,
        technicals=TechnicalIndicators(
            rsi_14=58.4,
            macd=1.25,
            macd_signal=0.87,
            macd_histogram=0.38,
            bb_upper=200.0,
            bb_middle=192.0,
            bb_lower=184.0,
            sma_20=191.5,
            sma_50=188.0,
            sma_200=175.0,
            adx=28.5,
            atr_14=3.20,
        ),
        fundamentals=CompanyFundamentals(
            market_cap=3_000_000_000_000,
            pe_ratio=28.5,
            forward_pe=25.2,
            peg_ratio=1.8,
            price_to_book=45.2,
            eps_ttm=6.85,
            eps_growth_yoy=0.12,
            revenue_growth_yoy=0.08,
            profit_margin=0.245,
            debt_to_equity=1.8,
            return_on_equity=1.45,
            beta=1.2,
            sector="Technology",
            industry="Consumer Electronics",
        ),
        technical_summary="Bullish momentum with price above all key moving averages.",
        fundamental_summary="High-quality business with strong margins and cash generation.",
    )


@pytest.fixture
def sample_sentiment_data() -> SentimentData:
    return SentimentData(
        ticker="AAPL",
        company_name="Apple Inc.",
        overall_score=0.42,
        reddit_score=0.35,
        news_score=0.50,
        label=SentimentLabel.BULLISH,
        total_mentions=1250,
        articles_analyzed=45,
        bullish_themes=["Strong iPhone cycle", "AI integration", "Services growth"],
        bearish_themes=["China headwinds", "Valuation premium", "Slowing hardware growth"],
        key_catalysts=["Q2 earnings in 4 weeks", "WWDC announcements", "India expansion"],
        sentiment_summary=(
            "Apple sentiment is broadly positive, driven by anticipation of the next iPhone "
            "release and growing services revenue. Institutional coverage remains constructive."
        ),
    )


@pytest.fixture
def sample_risk_metrics() -> RiskMetrics:
    return RiskMetrics(
        ticker="AAPL",
        historical_volatility_30d=0.22,
        historical_volatility_90d=0.24,
        value_at_risk_95=0.0185,
        value_at_risk_99=0.0263,
        expected_shortfall_95=0.0245,
        beta=1.18,
        sharpe_ratio=1.45,
        sortino_ratio=2.10,
        max_drawdown=-0.185,
        calmar_ratio=3.2,
        market_correlation=0.78,
        risk_level=RiskLevel.MODERATE,
    )


@pytest.fixture
def sample_recommendation(
    sample_stock_data: StockData,
    sample_sentiment_data: SentimentData,
    sample_risk_metrics: RiskMetrics,
) -> InvestmentRecommendation:
    return InvestmentRecommendation(
        ticker="AAPL",
        company_name="Apple Inc.",
        signal=Signal.BUY,
        confidence=0.72,
        risk_level=RiskLevel.MODERATE,
        target_price_bull=220.0,
        target_price_base=210.0,
        target_price_bear=185.0,
        stop_loss=188.0,
        time_horizon_days=60,
        technical_score=68.0,
        fundamental_score=72.0,
        sentiment_score=65.0,
        risk_adjusted_score=69.0,
        executive_summary=(
            "Apple presents a BUY opportunity with strong technical momentum, "
            "solid fundamentals, and positive sentiment heading into the product cycle."
        ),
        bull_case="Strong iPhone 17 super-cycle drives revenue beat; Services reaches $100B annual run rate.",
        bear_case="China market deterioration accelerates; macro slowdown hits consumer discretionary spend.",
        key_risks=["China regulatory risk", "AI monetization uncertainty", "Premium valuation"],
        key_catalysts=["Q2 earnings", "WWDC", "India market expansion"],
        market_data=sample_stock_data,
        sentiment_data=sample_sentiment_data,
        risk_metrics=sample_risk_metrics,
        agents_used=["market-data-agent", "sentiment-agent", "risk-agent"],
        analysis_duration_seconds=45.3,
    )
