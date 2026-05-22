"""Orchestrator entry point — starts FastAPI server or CLI mode."""
from __future__ import annotations

import asyncio
import json
import sys

import uvicorn

from shared.config import get_settings
from shared.logging import configure_logging


def start_server() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    uvicorn.run(
        "orchestrator.api:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


async def _cli_analyze(ticker: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    from orchestrator.coordinator import AgentCoordinator

    coordinator = AgentCoordinator(settings)
    try:
        recommendation = await coordinator.analyze(ticker)
        print(json.dumps(recommendation.to_summary(), indent=2))
    finally:
        await coordinator.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "analyze":
        asyncio.run(_cli_analyze(sys.argv[2]))
    else:
        start_server()
