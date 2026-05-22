"""Market Data Agent — standalone service entry point."""
from __future__ import annotations

import asyncio
import logging

from shared.config import get_settings
from shared.events import EventType, MarketDataEvent, AnalysisFailedEvent
from shared.logging import configure_logging
from shared.message_bus import lifespan_message_bus

from market_data_agent.agent import MarketDataAgent

logger = logging.getLogger(__name__)


async def run_service() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info("Market Data Agent service starting")

    agent = MarketDataAgent(settings)

    async with lifespan_message_bus(settings.redis_url) as bus:
        logger.info("Market Data Agent listening for requests")
        async for msg_id, raw in bus.consume(
            EventType.ANALYSIS_REQUESTED,
            group="market-data-agent",
            consumer="market-data-agent-1",
        ):
            ticker: str = raw.get("ticker", "")
            correlation_id: str = raw.get("correlation_id", "")
            logger.info("Processing analysis request", extra={"ticker": ticker})

            try:
                stock_data = await agent.analyze(ticker)
                event = MarketDataEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    data=stock_data,
                )
                await bus.publish(event)
                logger.info("Market data published", extra={"ticker": ticker})
            except Exception as exc:
                logger.exception("Market data analysis failed", extra={"ticker": ticker})
                error_event = AnalysisFailedEvent(
                    correlation_id=correlation_id,
                    ticker=ticker,
                    error=str(exc),
                    agent="market-data-agent",
                )
                await bus.publish(error_event)
            finally:
                await bus.ack(EventType.ANALYSIS_REQUESTED, "market-data-agent", msg_id)


if __name__ == "__main__":
    asyncio.run(run_service())
