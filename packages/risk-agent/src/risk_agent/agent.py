from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import litellm

from shared.config import Settings
from shared.llm_client import get_completion_kwargs
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

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior portfolio manager. Analyze the provided data and respond ONLY with a JSON object.

Decision rules:
- STRONG_BUY: risk-adjusted score ≥80, confidence ≥0.80, risk ≤ MODERATE
- BUY: risk-adjusted score ≥65, confidence ≥0.65
- HOLD: mixed signals or score 40-65
- SELL: score ≤35, confidence ≥0.65
- STRONG_SELL: score ≤20, confidence ≥0.80

Signal weights: technical 30%, fundamental 35%, sentiment 20%, risk 15%
"""

_RESPONSE_SCHEMA = """\
Respond with ONLY this JSON (no markdown, no explanation):
{
  "signal": "BUY|STRONG_BUY|HOLD|SELL|STRONG_SELL",
  "confidence": 0.0,
  "risk_level": "LOW|MODERATE|HIGH|VERY_HIGH",
  "target_price_bull": 0.0,
  "target_price_base": 0.0,
  "target_price_bear": 0.0,
  "stop_loss": 0.0,
  "time_horizon_days": 30,
  "technical_score": 0,
  "fundamental_score": 0,
  "sentiment_score": 0,
  "risk_adjusted_score": 0,
  "executive_summary": "...",
  "bull_case": "...",
  "bear_case": "...",
  "key_risks": ["..."],
  "key_catalysts": ["..."]
}"""


class RiskAgent:
    """
    Risk analyst: one LLM call per analysis (all data in prompt).
    ~4K tokens vs previous ~17K multi-tool-call approach.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.risk_agent_model
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

        prompt = self._build_prompt(stock_data, sentiment_data, chart_analysis, risk_metrics_raw)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        result = await self._call_with_retry(messages)
        duration = time.monotonic() - start

        recommendation = self._build_recommendation(
            stock_data=stock_data,
            sentiment_data=sentiment_data,
            risk_metrics=risk_metrics,
            result=result,
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

    def _build_prompt(
        self,
        sd: StockData,
        sent: SentimentData,
        ca: ChartAnalysis | None,
        risk_raw: dict[str, Any],
    ) -> str:
        t = sd.technicals
        f = sd.fundamentals

        lines = [
            f"Analyze {sd.ticker} ({sd.company_name}) at ${sd.current_price:.2f}:",
            "",
            "MARKET DATA:",
            f"  Price change: {sd.price_change_pct:.1f}%  52w H/L: {sd.week_52_high}/{sd.week_52_low}",
            f"  RSI: {t.rsi_14}  MACD: {t.macd}/{t.macd_signal}  ADX: {t.adx}",
            f"  SMA50: {t.sma_50}  SMA200: {t.sma_200}  ATR: {t.atr_14}",
            f"  P/E: {f.pe_ratio}  Fwd P/E: {f.forward_pe}  PEG: {f.peg_ratio}  Beta: {f.beta}",
            f"  ROE: {f.return_on_equity}  Rev growth: {f.revenue_growth_yoy}  Margin: {f.profit_margin}",
            f"  D/E: {f.debt_to_equity}  Sector: {f.sector}",
        ]
        if sd.technical_summary:
            lines.append(f"  Technical: {sd.technical_summary[:200]}")
        if sd.fundamental_summary:
            lines.append(f"  Fundamental: {sd.fundamental_summary[:200]}")

        lines += [
            "",
            "SENTIMENT:",
            f"  Label: {sent.label}  Score: {sent.overall_score}  Mentions: {sent.total_mentions}",
        ]
        if sent.sentiment_summary:
            lines.append(f"  {sent.sentiment_summary[:200]}")

        if ca:
            lines += [
                "",
                "CHART:",
                f"  Trend: {ca.trend} ({ca.trend_strength})  Signal: {ca.chart_signal}  Conf: {ca.confidence}",
                f"  Support: {ca.support_levels[:3]}  Resistance: {ca.resistance_levels[:3]}",
            ]
            if ca.patterns:
                lines.append(f"  Patterns: {[p.name for p in ca.patterns[:3]]}")
            if ca.chart_summary:
                lines.append(f"  {ca.chart_summary[:200]}")

        lines += [
            "",
            "RISK METRICS:",
            f"  Vol30d: {risk_raw.get('historical_volatility_30d')}  VaR95: {risk_raw.get('value_at_risk_95')}",
            f"  Beta: {risk_raw.get('beta')}  Sharpe: {risk_raw.get('sharpe_ratio')}  MaxDD: {risk_raw.get('max_drawdown')}",
            "",
            _RESPONSE_SCHEMA,
        ]
        return "\n".join(lines)

    @staticmethod
    def _parse_retry_seconds(error_str: str) -> float:
        m = re.search(r"try again in (?:(\d+)m\s*)?([0-9.]+)s", error_str)
        if not m:
            return 35.0
        return float(m.group(1) or 0) * 60 + float(m.group(2)) + 3.0

    async def _call_with_retry(self, messages: list[dict[str, Any]], max_retries: int = 4) -> dict[str, Any]:
        """Single LLM call; on TPM RateLimitError sleep and retry; on TPD raise immediately."""
        for attempt in range(max_retries):
            try:
                response = await litellm.acompletion(
                    model=self._model,
                    max_tokens=1024,
                    messages=messages,
                    **self._completion_kwargs,
                )
                content = response.choices[0].message.content or ""
                return self._parse_json(content)
            except litellm.RateLimitError as exc:
                err = str(exc)
                if "per day" in err or "tokens per day" in err or "TPD" in err:
                    logger.error("Groq daily token quota (TPD) exhausted — stopping analysis")
                    raise
                if attempt == max_retries - 1:
                    raise
                wait = self._parse_retry_seconds(err)
                logger.warning("Groq TPM rate limit — retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, max_retries)
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Extract JSON from model response, stripping markdown fences if present."""
        content = content.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        logger.warning("RiskAgent: could not parse JSON from response, returning empty")
        return {}

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
