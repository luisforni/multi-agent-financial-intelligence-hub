from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from shared.models import InvestmentRecommendation, SentimentData, StockData


class EventType(StrEnum):
    ANALYSIS_REQUESTED = "analysis.requested"
    MARKET_DATA_READY = "market_data.ready"
    SENTIMENT_READY = "sentiment.ready"
    RECOMMENDATION_READY = "recommendation.ready"
    ANALYSIS_FAILED = "analysis.failed"


class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    correlation_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ticker: str


class AnalysisRequestedEvent(BaseEvent):
    event_type: EventType = EventType.ANALYSIS_REQUESTED


class MarketDataEvent(BaseEvent):
    event_type: EventType = EventType.MARKET_DATA_READY
    data: StockData


class SentimentEvent(BaseEvent):
    event_type: EventType = EventType.SENTIMENT_READY
    data: SentimentData


class RecommendationEvent(BaseEvent):
    event_type: EventType = EventType.RECOMMENDATION_READY
    data: InvestmentRecommendation


class AnalysisFailedEvent(BaseEvent):
    event_type: EventType = EventType.ANALYSIS_FAILED
    error: str
    agent: str


# Stream names per event type
STREAM_NAMES: dict[EventType, str] = {
    EventType.ANALYSIS_REQUESTED: "stream:analysis:requests",
    EventType.MARKET_DATA_READY: "stream:market_data",
    EventType.SENTIMENT_READY: "stream:sentiment",
    EventType.RECOMMENDATION_READY: "stream:recommendations",
    EventType.ANALYSIS_FAILED: "stream:errors",
}
