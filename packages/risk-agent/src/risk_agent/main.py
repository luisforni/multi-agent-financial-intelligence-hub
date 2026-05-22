"""Risk Agent — standalone service entry point."""
from __future__ import annotations

import asyncio
import json
import logging

from shared.config import get_settings
from shared.events import (
    EventType,
    MarketDataEvent,
    SentimentEvent,
    RecommendationEvent,
    AnalysisFailedEvent,
)
from shared.logging import configure_logging
from shared.message_bus import lifespan_message_bus

from risk_agent.agent import RiskAgent

logger = logging.getLogger(__name__)


async def run_service() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info("Risk Agent service starting")

    agent = RiskAgent(settings)

    async with lifespan_message_bus(settings.redis_url) as bus:
        logger.info("Risk Agent listening for market data")
        async for msg_id, raw in bus.consume(
            EventType.MARKET_DATA_READY,
            group="risk-agent",
            consumer="risk-agent-1",
        ):
            ticker: str = raw.get("ticker", "")
            correlation_id: str = raw.get("correlation_id", "")
            logger.info("Received market data, waiting for sentiment", extra={"ticker": ticker})

            try:
                market_event = MarketDataEvent(**raw)
                stock_data = market_event.data

                # Wait for sentiment data with the same correlation_id
                sentiment_raw = await bus.read_one(
                    EventType.SENTIMENT_READY,
                    correlation_id=correlation_id,
                    timeout_ms=settings.max_analysis_timeout_seconds * 1000,
                )
                if not sentiment_raw:
                    raise TimeoutError(f"Sentiment data not received within timeout for {ticker}")

                sentiment_event = SentimentEvent(**sentiment_raw)
                sentiment_data = sentiment_event.data

                recommendation = await agent.analyze(stock_data, sentiment_data)
                event = RecommendationEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    data=recommendation,
                )
                await bus.publish(event)
                logger.info(
                    "Recommendation published",
                    extra={
                        "ticker": ticker,
                        "signal": recommendation.signal,
                        "confidence": recommendation.confidence,
                    },
                )
            except Exception as exc:
                logger.exception("Risk analysis failed", extra={"ticker": ticker})
                error_event = AnalysisFailedEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    error=str(exc),
                    agent="risk-agent",
                )
                await bus.publish(error_event)
            finally:
                await bus.ack(EventType.MARKET_DATA_READY, "risk-agent", msg_id)


if __name__ == "__main__":
    asyncio.run(run_service())
