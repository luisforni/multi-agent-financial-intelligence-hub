"""Standalone entry point for local testing."""
from __future__ import annotations

import asyncio
import json
import sys

from shared.config import get_settings
from shared.logging import configure_logging

from chart_vision_agent.agent import ChartVisionAgent


async def main(ticker: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    agent = ChartVisionAgent(settings)
    result = await agent.analyze(ticker)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    asyncio.run(main(ticker))
