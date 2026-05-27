from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from shared.config import Settings
from shared.events import EventType, RecommendationEvent
from shared.message_bus import MessageBus
from shared.models import ChartAnalysis, InvestmentRecommendation, SentimentData

from market_data_agent.agent import MarketDataAgent
from sentiment_agent.agent import SentimentAgent
from risk_agent.agent import RiskAgent
from chart_vision_agent.agent import ChartVisionAgent

from orchestrator.workflow import WorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Orchestrates the four-agent pipeline:

      1. MarketDataAgent  ─┐
      2. SentimentAgent   ─┤─► RiskAgent ─► InvestmentRecommendation
      3. ChartVisionAgent ─┘

    The first three agents run concurrently (asyncio.gather),
    then the risk agent synthesizes all outputs.
    """

    def __init__(
        self,
        settings: Settings,
        message_bus: MessageBus | None = None,
    ) -> None:
        self._settings = settings
        self._bus = message_bus
        self._market_agent = MarketDataAgent(settings)
        self._sentiment_agent = SentimentAgent(settings)
        self._risk_agent = RiskAgent(settings)
        self._chart_agent = ChartVisionAgent(settings)

    async def analyze(
        self,
        ticker: str,
        on_progress=None,
        cached_sentiment: SentimentData | None = None,
    ) -> InvestmentRecommendation:
        """
        on_progress: optional async callable(step: str, message: str) called as each
        agent completes so the caller can broadcast intermediate WebSocket events.
        cached_sentiment: when provided (market-hours fast path), skip the sentiment
        agent and use this pre-computed data instead, running only market-data + chart.
        """
        ticker = ticker.upper().strip()
        workflow = WorkflowState(ticker=ticker)
        workflow.status = WorkflowStatus.RUNNING

        logger.info(
            "Starting multi-agent analysis",
            extra={
                "ticker": ticker,
                "workflow_id": workflow.workflow_id,
                "fast_path": cached_sentiment is not None,
            },
        )

        async def _step(coro, step: str, summarize):
            result = await coro
            if on_progress:
                try:
                    await on_progress(step, summarize(result))
                except Exception:
                    pass
            return result

        try:
            # Stage 1: Parallel data gathering
            market_task = asyncio.create_task(
                _step(
                    self._market_agent.analyze(ticker),
                    "market_data",
                    lambda r: (
                        f"${r.current_price:.2f}"
                        + (f" · RSI {r.technicals.rsi_14:.0f}" if r.technicals and r.technicals.rsi_14 else "")
                        + (f" · {r.technical_summary[:80]}" if r.technical_summary else "")
                    ),
                ),
                name=f"market-{ticker}",
            )
            chart_task = asyncio.create_task(
                _step(
                    self._chart_agent.analyze(ticker),
                    "chart",
                    lambda r: (
                        (f"{r.trend}" if r.trend else "no trend")
                        + (f" · {r.chart_signal}" if r.chart_signal else "")
                        + (f" · patterns: {', '.join(p.name for p in r.patterns[:3])}" if r.patterns else " · no patterns")
                    ),
                ),
                name=f"chart-{ticker}",
            )

            if cached_sentiment is not None:
                # Fast path (market hours): market-data + chart only, reuse cached sentiment
                market_data, chart_analysis = await asyncio.gather(market_task, chart_task)
                sentiment_data = cached_sentiment
                if on_progress:
                    try:
                        score = cached_sentiment.overall_score
                        await on_progress(
                            "sentiment",
                            f"cached · {cached_sentiment.label}"
                            + (f" · score {score:+.2f}" if score is not None else ""),
                        )
                    except Exception:
                        pass
            else:
                # Full path (overnight / fallback): market-data + sentiment + chart in parallel
                sentiment_task = asyncio.create_task(
                    _step(
                        self._run_sentiment(ticker),
                        "sentiment",
                        lambda r: (
                            f"{r.label}"
                            + (f" · score {r.overall_score:+.2f}" if r.overall_score is not None else "")
                            + (f" · {r.sentiment_summary[:80]}" if r.sentiment_summary else "")
                        ),
                    ),
                    name=f"sentiment-{ticker}",
                )
                market_data, sentiment_data, chart_analysis = await asyncio.gather(
                    market_task, sentiment_task, chart_task
                )

            workflow.mark_step("market_data")
            workflow.mark_step("sentiment")
            workflow.mark_step("chart_analysis")

            logger.info(
                "Parallel data gathering complete",
                extra={
                    "ticker": ticker,
                    "company": market_data.company_name,
                    "sentiment_label": sentiment_data.label,
                    "chart_signal": chart_analysis.chart_signal,
                    "chart_trend": chart_analysis.trend,
                    "sentiment_cached": cached_sentiment is not None,
                },
            )

            # Stage 2: Risk analysis + recommendation
            recommendation = await self._risk_agent.analyze(
                market_data, sentiment_data, chart_analysis
            )
            recommendation.chart_analysis = chart_analysis
            workflow.mark_step("risk_analysis")
            if on_progress:
                try:
                    await on_progress(
                        "risk",
                        f"{recommendation.signal} · {round(recommendation.confidence * 100)}% confidence · {recommendation.risk_level}",
                    )
                except Exception:
                    pass
            workflow.complete(recommendation)

            if self._bus:
                await self._bus.publish(
                    RecommendationEvent(
                        correlation_id=workflow.workflow_id,
                        ticker=ticker,
                        data=recommendation,
                    )
                )

            logger.info(
                "Analysis pipeline complete",
                extra={
                    "ticker": ticker,
                    "signal": recommendation.signal,
                    "confidence": recommendation.confidence,
                    "duration_s": workflow.duration_seconds,
                },
            )
            return recommendation

        except Exception as exc:
            workflow.fail(str(exc))
            logger.exception(
                "Analysis pipeline failed",
                extra={"ticker": ticker, "workflow_id": workflow.workflow_id},
            )
            raise

    async def _run_sentiment(self, ticker: str) -> Any:
        try:
            import yfinance as yf
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info or {})
            company_name = info.get("longName") or info.get("shortName") or ticker
        except Exception:
            company_name = ticker
        return await self._sentiment_agent.analyze(ticker, company_name)

    async def close(self) -> None:
        await self._market_agent.close()
        await self._sentiment_agent.close()
