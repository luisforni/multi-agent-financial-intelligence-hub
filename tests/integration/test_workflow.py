"""Integration tests — require real API keys and network access."""
from __future__ import annotations

import pytest

from shared.models import InvestmentRecommendation, Signal

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_full_pipeline_aapl(mock_settings) -> None:  # type: ignore[no-untyped-def]
    """Full end-to-end pipeline test for AAPL — requires real credentials."""
    from orchestrator.coordinator import AgentCoordinator

    coordinator = AgentCoordinator(mock_settings)
    try:
        result = await coordinator.analyze("AAPL")
        assert isinstance(result, InvestmentRecommendation)
        assert result.ticker == "AAPL"
        assert result.signal in list(Signal)
        assert 0.0 <= result.confidence <= 1.0
        assert result.current_price > 0 if result.market_data else True
        assert len(result.agents_used) == 3
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_full_pipeline_invalid_ticker(mock_settings) -> None:  # type: ignore[no-untyped-def]
    """Invalid ticker should raise an exception."""
    from orchestrator.coordinator import AgentCoordinator

    coordinator = AgentCoordinator(mock_settings)
    try:
        with pytest.raises(Exception):
            await coordinator.analyze("XXXXXXXXXX")
    finally:
        await coordinator.close()
