"""Sentiment Agent — standalone service entry point."""
from __future__ import annotations

import asyncio
import logging

from shared.config import get_settings
from shared.events import EventType, SentimentEvent, AnalysisFailedEvent
from shared.logging import configure_logging
from shared.message_bus import lifespan_message_bus

from sentiment_agent.agent import SentimentAgent

logger = logging.getLogger(__name__)


async def run_service() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info("Sentiment Agent service starting")

    agent = SentimentAgent(settings)

    async with lifespan_message_bus(settings.redis_url) as bus:
        logger.info("Sentiment Agent listening for requests")
        async for msg_id, raw in bus.consume(
            EventType.ANALYSIS_REQUESTED,
            group="sentiment-agent",
            consumer="sentiment-agent-1",
        ):
            ticker: str = raw.get("ticker", "")
            company_name: str = raw.get("company_name", ticker)
            correlation_id: str = raw.get("correlation_id", "")
            logger.info("Processing sentiment request", extra={"ticker": ticker})

            try:
                sentiment_data = await agent.analyze(ticker, company_name)
                event = SentimentEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    data=sentiment_data,
                )
                await bus.publish(event)
                logger.info("Sentiment data published", extra={"ticker": ticker})
            except Exception as exc:
                logger.exception("Sentiment analysis failed", extra={"ticker": ticker})
                error_event = AnalysisFailedEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    error=str(exc),
                    agent="sentiment-agent",
                )
                await bus.publish(error_event)
            finally:
                await bus.ack(EventType.ANALYSIS_REQUESTED, "sentiment-agent", msg_id)


if __name__ == "__main__":
    asyncio.run(run_service())
