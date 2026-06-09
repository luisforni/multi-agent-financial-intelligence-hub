from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import litellm

from shared.config import Settings
from shared.llm_client import get_completion_kwargs, tool_call_to_dict
from shared.models import (
    ChartAnalysis,
    InvestmentRecommendation,
    RiskLevel,
    RiskMetrics,
    SentimentData,
    Signal,
    StockData,
)

from risk_agent.scorers.risk_scorer import RiskScorer
from risk_agent.scorers.portfolio import PortfolioAnalyzer
from risk_agent.tools import RISK_TOOLS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior portfolio manager and quantitative risk analyst at a tier-1 investment firm.
You synthesize technical analysis, fundamental data, sentiment signals, and quantitative risk metrics \
to produce institutional-grade investment recommendations.

Your recommendation framework:
1. **Signal Aggregation**: Weigh technical (30%), fundamental (35%), sentiment (20%), risk (15%)
2. **Risk-Adjusted Conviction**: Only issue STRONG BUY/SELL signals with >75% confidence
3. **Scenario Analysis**: Always define bull, base, and bear cases with price targets
4. **Risk Identification**: Be explicit about tail risks, not just average-case scenarios
5. **Time Horizon**: Calibrate to medium-term (30-90 day) unless specifically justified
6. **Contrarian Check**: When sentiment is extreme, consider the contrarian view

Decision rules:
- STRONG_BUY: Risk-adjusted score ≥80, confidence ≥0.80, risk ≤ MODERATE
- BUY: Risk-adjusted score ≥65, confidence ≥0.65
- HOLD: Mixed signals or risk-adjusted score 40-65
- SELL: Risk-adjusted score ≤35, confidence ≥0.65
- STRONG_SELL: Risk-adjusted score ≤20, confidence ≥0.80

Use ALL available tools to gather data before forming your recommendation.
Your analysis must be evidence-based, not opinion-based. Cite specific metrics.
"""


class RiskAgent:
    """
    Agentic risk analyst and recommendation engine powered by any LiteLLM-compatible provider.

    Synthesizes market data + sentiment into actionable investment recommendations
    with quantitative risk metrics, price targets, and position sizing.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.risk_agent_model
        self._fallbacks = settings.risk_agent_fallback_list
        self._completion_kwargs = get_completion_kwargs(settings, self._model)
        self._risk_scorer = RiskScorer()
        self._portfolio = PortfolioAnalyzer()

    async def analyze(
        self,
        stock_data: StockData,
        sentiment_data: SentimentData,
        chart_analysis: ChartAnalysis | None = None,
    ) -> InvestmentRecommendation:
        ticker = stock_data.ticker
        logger.info("RiskAgent starting analysis", extra={"ticker": ticker})
        start = time.monotonic()

        risk_metrics_raw = await self._risk_scorer.compute(ticker)
        risk_metrics = self._build_risk_metrics(ticker, risk_metrics_raw)

        cache: dict[str, Any] = {
            "stock_data": stock_data,
            "sentiment_data": sentiment_data,
            "risk_metrics": risk_metrics_raw,
            "chart_analysis": chart_analysis,
        }

        chart_note = (
            f" Chart analysis is also available (signal: {chart_analysis.chart_signal}, "
            f"trend: {chart_analysis.trend})."
            if chart_analysis else ""
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate a comprehensive investment recommendation for **{ticker}** "
                    f"({stock_data.company_name}) at current price ${stock_data.current_price:.2f}. "
                    f"Market data analysis, sentiment analysis, and chart vision analysis have already been completed.{chart_note} "
                    f"Use all available tools to retrieve the data, then submit your final recommendation."
                ),
            },
        ]

        recommendation_result: dict[str, Any] | None = None

        while True:
            response = await self._call_with_retry(messages)

            choice = response.choices[0]

            if choice.finish_reason == "stop":
                break

            tool_calls = getattr(choice.message, "tool_calls", None) or []
            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [tool_call_to_dict(tc) for tc in tool_calls],
            })

            for tc in tool_calls:
                tool_name = tc.function.name
                tool_input: dict[str, Any] = json.loads(tc.function.arguments)

                result = await self._execute_tool(tool_name, tool_input, cache)

                if tool_name == "submit_recommendation":
                    recommendation_result = tool_input

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

            if recommendation_result is not None:
                break

        duration = time.monotonic() - start
        recommendation = self._build_recommendation(
            stock_data=stock_data,
            sentiment_data=sentiment_data,
            risk_metrics=risk_metrics,
            result=recommendation_result or {},
            duration=duration,
        )
        logger.info(
            "RiskAgent recommendation issued",
            extra={
                "ticker": ticker,
                "signal": recommendation.signal,
                "confidence": recommendation.confidence,
                "duration_s": round(duration, 2),
            },
        )
        return recommendation

    @staticmethod
    def _parse_retry_seconds(error_str: str) -> float:
        """Parse 'try again in Xm Y.Zs' or 'try again in Y.Zs' into total seconds."""
        m = re.search(r"try again in (?:(\d+)m\s*)?([0-9.]+)s", error_str)
        if not m:
            return 35.0
        minutes = float(m.group(1) or 0)
        seconds = float(m.group(2))
        return minutes * 60 + seconds + 3.0

    async def _call_with_retry(self, messages: list[dict[str, Any]], max_retries: int = 4) -> Any:
        """Call litellm without fallbacks; on TPM RateLimitError sleep and retry; on TPD raise immediately."""
        for attempt in range(max_retries):
            try:
                return await litellm.acompletion(
                    model=self._model,
                    max_tokens=2048,
                    messages=messages,
                    tools=RISK_TOOLS,
                    parallel_tool_calls=False,
                    **self._completion_kwargs,
                )
            except litellm.RateLimitError as exc:
                err = str(exc)
                # Daily quota exhausted — no point retrying, raises immediately
                if "per day" in err or "tokens per day" in err or "TPD" in err:
                    logger.error("Groq daily token quota (TPD) exhausted — stopping analysis")
                    raise
                if attempt == max_retries - 1:
                    raise
                wait = self._parse_retry_seconds(err)
                logger.warning(
                    "Groq TPM rate limit — retrying in %.1fs (attempt %d/%d)",
                    wait, attempt + 1, max_retries,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _execute_tool(
        self, name: str, input_data: dict[str, Any], cache: dict[str, Any]
    ) -> Any:
        logger.debug("Executing tool", extra={"tool": name})

        if name == "get_quantitative_risk_metrics":
            return cache["risk_metrics"]

        if name == "get_market_data_summary":
            sd: StockData = cache["stock_data"]
            t = sd.technicals
            f = sd.fundamentals
            return {
                "ticker": sd.ticker,
                "company": sd.company_name,
                "sector": f.sector,
                "price": sd.current_price,
                "change_pct": sd.price_change_pct,
                "week_52_high": sd.week_52_high,
                "week_52_low": sd.week_52_low,
                "rsi_14": t.rsi_14,
                "macd": t.macd,
                "macd_signal": t.macd_signal,
                "sma_50": t.sma_50,
                "sma_200": t.sma_200,
                "adx": t.adx,
                "atr_14": t.atr_14,
                "pe_ratio": f.pe_ratio,
                "forward_pe": f.forward_pe,
                "peg_ratio": f.peg_ratio,
                "beta": f.beta,
                "debt_to_equity": f.debt_to_equity,
                "return_on_equity": f.return_on_equity,
                "revenue_growth_yoy": f.revenue_growth_yoy,
                "profit_margin": f.profit_margin,
                "technical_summary": (sd.technical_summary or "")[:300],
                "fundamental_summary": (sd.fundamental_summary or "")[:300],
            }

        if name == "get_sentiment_summary":
            sent: SentimentData = cache["sentiment_data"]
            return {
                "ticker": sent.ticker,
                "overall_score": sent.overall_score,
                "label": sent.label,
                "reddit_score": sent.reddit_score,
                "news_score": sent.news_score,
                "total_mentions": sent.total_mentions,
                "sentiment_summary": (sent.sentiment_summary or "")[:300],
            }

        if name == "compute_position_sizing":
            sd = cache["stock_data"]
            direction = input_data.get("signal_direction", "bullish")
            portfolio_value = input_data.get("portfolio_value", 100_000.0)
            atr = sd.technicals.atr_14 or (sd.current_price * 0.02)

            sizing = self._portfolio.position_size_from_atr(
                portfolio_value=portfolio_value,
                atr=atr,
                current_price=sd.current_price,
            )
            targets = self._portfolio.compute_price_targets(
                current_price=sd.current_price,
                atr=atr,
                signal_direction=direction,
            )
            return {**sizing, **targets}

        if name == "get_chart_analysis":
            ca: ChartAnalysis | None = cache.get("chart_analysis")
            if ca is None:
                return {"available": False, "reason": "Chart vision analysis was not performed"}
            return {
                "available": True,
                "ticker": ca.ticker,
                "timeframe": ca.timeframe,
                "trend": ca.trend,
                "trend_strength": ca.trend_strength,
                "chart_signal": ca.chart_signal,
                "confidence": ca.confidence,
                "patterns": [
                    {"name": p.name, "confidence": p.confidence, "implication": p.implication}
                    for p in ca.patterns
                ],
                "support_levels": ca.support_levels,
                "resistance_levels": ca.resistance_levels,
                "chart_summary": (ca.chart_summary or "")[:300],
                "used_vision": ca.used_vision,
            }

        if name == "submit_recommendation":
            return {"status": "submitted"}

        return {"error": f"Unknown tool: {name}"}

    @staticmethod
    def _to_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str) and value.strip():
            items = [re.sub(r'^\s*\d+[\.\)]\s*', '', line).strip() for line in value.splitlines()]
            return [i for i in items if i]
        return []

    def _build_recommendation(
        self,
        stock_data: StockData,
        sentiment_data: SentimentData,
        risk_metrics: RiskMetrics,
        result: dict[str, Any],
        duration: float,
    ) -> InvestmentRecommendation:
        signal_str = result.get("signal", "HOLD")
        try:
            signal = Signal(signal_str)
        except ValueError:
            signal = Signal.HOLD

        risk_level_str = result.get("risk_level", "MODERATE")
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.MODERATE

        atr = stock_data.technicals.atr_14 or (stock_data.current_price * 0.02)
        direction = "bullish" if signal in (Signal.BUY, Signal.STRONG_BUY) else "bearish"
        targets = self._portfolio.compute_price_targets(stock_data.current_price, atr, direction)

        return InvestmentRecommendation(
            ticker=stock_data.ticker,
            company_name=stock_data.company_name,
            signal=signal,
            confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
            risk_level=risk_level,
            target_price_bull=result.get("target_price_bull") or targets["target_bull"],
            target_price_base=result.get("target_price_base") or targets["target_base"],
            target_price_bear=result.get("target_price_bear") or targets["target_bear"],
            stop_loss=result.get("stop_loss") or targets["stop_loss"],
            time_horizon_days=result.get("time_horizon_days", 30),
            technical_score=result.get("technical_score"),
            fundamental_score=result.get("fundamental_score"),
            sentiment_score=result.get("sentiment_score"),
            risk_adjusted_score=result.get("risk_adjusted_score"),
            executive_summary=result.get("executive_summary", "Analysis pending."),
            bull_case=result.get("bull_case", ""),
            bear_case=result.get("bear_case", ""),
            key_risks=self._to_list(result.get("key_risks", [])),
            key_catalysts=self._to_list(result.get("key_catalysts", [])),
            market_data=stock_data,
            sentiment_data=sentiment_data,
            risk_metrics=risk_metrics,
            agents_used=["market-data-agent", "sentiment-agent", "chart-vision-agent", "risk-agent"],
            analysis_duration_seconds=round(duration, 2),
        )

    @staticmethod
    def _build_risk_metrics(ticker: str, raw: dict[str, Any]) -> RiskMetrics:
        vol_30 = raw.get("historical_volatility_30d", 0.0)
        risk_level = (
            RiskLevel.VERY_HIGH if vol_30 > 0.70
            else RiskLevel.HIGH if vol_30 > 0.45
            else RiskLevel.MODERATE if vol_30 > 0.25
            else RiskLevel.LOW if vol_30 > 0.15
            else RiskLevel.VERY_LOW
        )
        return RiskMetrics(
            ticker=ticker,
            historical_volatility_30d=raw.get("historical_volatility_30d"),
            historical_volatility_90d=raw.get("historical_volatility_90d"),
            value_at_risk_95=raw.get("value_at_risk_95"),
            value_at_risk_99=raw.get("value_at_risk_99"),
            expected_shortfall_95=raw.get("expected_shortfall_95"),
            beta=raw.get("beta"),
            sharpe_ratio=raw.get("sharpe_ratio"),
            sortino_ratio=raw.get("sortino_ratio"),
            max_drawdown=raw.get("max_drawdown"),
            calmar_ratio=raw.get("calmar_ratio"),
            market_correlation=raw.get("market_correlation"),
            risk_level=risk_level,
        )
