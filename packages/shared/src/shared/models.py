from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Signal(StrEnum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class RiskLevel(StrEnum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class SentimentLabel(StrEnum):
    VERY_BULLISH = "VERY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    VERY_BEARISH = "VERY_BEARISH"


class TradeDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class TechnicalIndicators(BaseModel):
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    adx: float | None = None
    stochastic_k: float | None = None
    stochastic_d: float | None = None
    volume_sma_20: float | None = None
    atr_14: float | None = None


class CompanyFundamentals(BaseModel):
    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    ev_to_ebitda: float | None = None
    eps_ttm: float | None = None
    eps_growth_yoy: float | None = None
    revenue_growth_yoy: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    dividend_yield: float | None = None
    beta: float | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None
    short_ratio: float | None = None
    sector: str | None = None
    industry: str | None = None


class StockData(BaseModel):
    ticker: str
    company_name: str
    exchange: str | None = None
    currency: str = "USD"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    current_price: float
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    previous_close: float | None = None
    price_change: float | None = None
    price_change_pct: float | None = None
    volume: int | None = None
    average_volume: int | None = None

    technicals: TechnicalIndicators = Field(default_factory=TechnicalIndicators)
    fundamentals: CompanyFundamentals = Field(default_factory=CompanyFundamentals)

    week_52_high: float | None = None
    week_52_low: float | None = None

    technical_summary: str | None = None
    fundamental_summary: str | None = None

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.upper().strip()


class SentimentSource(BaseModel):
    source: str
    mention_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    avg_score: float = 0.0
    sample_texts: list[str] = Field(default_factory=list, max_length=5)


class SentimentData(BaseModel):
    ticker: str
    company_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    overall_score: float = 0.0
    reddit_score: float | None = None
    news_score: float | None = None
    social_score: float | None = None

    label: SentimentLabel = SentimentLabel.NEUTRAL

    sources: list[SentimentSource] = Field(default_factory=list)

    total_mentions: int = 0
    articles_analyzed: int = 0

    bullish_themes: list[str] = Field(default_factory=list)
    bearish_themes: list[str] = Field(default_factory=list)

    sentiment_summary: str | None = None
    key_catalysts: list[str] = Field(default_factory=list)


class RiskMetrics(BaseModel):
    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    historical_volatility_30d: float | None = None
    historical_volatility_90d: float | None = None
    implied_volatility: float | None = None

    value_at_risk_95: float | None = None
    value_at_risk_99: float | None = None
    expected_shortfall_95: float | None = None
    beta: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: float | None = None
    calmar_ratio: float | None = None

    market_correlation: float | None = None
    sector_relative_strength: float | None = None

    risk_level: RiskLevel = RiskLevel.MODERATE

    risk_summary: str | None = None


class ChartPattern(BaseModel):
    name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    implication: str  # "bullish" or "bearish"


class ChartAnalysis(BaseModel):
    ticker: str
    timeframe: str = "daily"
    trend: str  # "uptrend", "downtrend", "sideways"
    trend_strength: str = "moderate"  # "strong", "moderate", "weak"
    patterns: list[ChartPattern] = Field(default_factory=list)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    chart_signal: str = "HOLD"  # "BUY", "SELL", "HOLD"
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    chart_summary: str = ""
    used_vision: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TechnicalSignal(BaseModel):
    signal_type: str
    direction: str  # "bullish" or "bearish"
    strength: float = Field(..., ge=0.0, le=1.0)
    description: str


class ScannerAlert(BaseModel):
    ticker: str
    company_name: str
    current_price: float
    change_pct: float | None = None
    signals: list[TechnicalSignal]
    combined_score: float  # -1.0 (strong sell) to +1.0 (strong buy)
    alert_direction: str  # "bullish", "bearish", "neutral"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InvestmentRecommendation(BaseModel):
    ticker: str
    company_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    signal: Signal
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel

    target_price_bull: float | None = None
    target_price_base: float | None = None
    target_price_bear: float | None = None
    stop_loss: float | None = None

    time_horizon_days: int | None = None

    technical_score: float | None = None
    fundamental_score: float | None = None
    sentiment_score: float | None = None
    risk_adjusted_score: float | None = None

    executive_summary: str
    bull_case: str
    bear_case: str
    key_risks: list[str] = Field(default_factory=list)
    key_catalysts: list[str] = Field(default_factory=list)

    market_data: StockData | None = None
    sentiment_data: SentimentData | None = None
    risk_metrics: RiskMetrics | None = None

    agents_used: list[str] = Field(default_factory=list)
    analysis_duration_seconds: float | None = None

    chart_analysis: ChartAnalysis | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "signal": self.signal,
            "confidence": f"{self.confidence:.1%}",
            "risk_level": self.risk_level,
            "target_price_base": self.target_price_base,
            "stop_loss": self.stop_loss,
            "executive_summary": self.executive_summary,
        }


class Position(BaseModel):
    ticker: str
    company_name: str
    direction: TradeDirection
    entry_price: float
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    quantity: float = 100.0
    stop_loss: float | None = None
    target_price: float | None = None
    current_price: float | None = None
    signal: str = "BUY"

    def unrealized_pnl(self) -> float | None:
        if self.current_price is None:
            return None
        mult = 1.0 if self.direction == TradeDirection.LONG else -1.0
        return (self.current_price - self.entry_price) * self.quantity * mult

    def unrealized_pnl_pct(self) -> float | None:
        if self.current_price is None or self.entry_price == 0:
            return None
        mult = 1.0 if self.direction == TradeDirection.LONG else -1.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100.0 * mult


class ClosedTrade(BaseModel):
    ticker: str
    company_name: str
    direction: TradeDirection
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime = Field(default_factory=datetime.utcnow)
    quantity: float
    realized_pnl: float
    realized_pnl_pct: float
    exit_reason: str  # "stop_loss" | "take_profit" | "signal_reversal" | "manual"
