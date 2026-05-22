from __future__ import annotations

import json
import logging
import time
from typing import Any

import litellm

from shared.config import Settings
from shared.llm_client import get_completion_kwargs
from shared.models import ChartAnalysis, ChartPattern

from chart_vision_agent.chart_generator import (
    build_text_description,
    fetch_ohlcv,
    generate_chart_image,
)

logger = logging.getLogger(__name__)

# Vision-capable model identifiers (prefix match)
_VISION_PREFIXES = ("ollama/llava", "ollama/llava-llama3", "openai/gpt-4o", "gpt-4o", "gemini/")

_SYSTEM_PROMPT = """\
You are an expert technical analyst specializing in chart pattern recognition and price action trading.

Analyze the provided stock chart and identify:
1. **Primary trend**: uptrend / downtrend / sideways, and its strength (strong / moderate / weak)
2. **Chart patterns**: identify any classic patterns (Head & Shoulders, Double Top/Bottom, Cup & Handle,
   Bull/Bear Flag, Triangle, Wedge, Channel, etc.) with confidence level
3. **Key support levels**: price levels where buying interest has historically emerged
4. **Key resistance levels**: price levels where selling pressure has historically appeared
5. **Overall signal**: BUY / SELL / HOLD with confidence (0.0–1.0)

Respond ONLY with valid JSON matching this schema exactly:
{
  "trend": "uptrend|downtrend|sideways",
  "trend_strength": "strong|moderate|weak",
  "patterns": [
    {"name": "...", "confidence": 0.0-1.0, "implication": "bullish|bearish"}
  ],
  "support_levels": [float, ...],
  "resistance_levels": [float, ...],
  "chart_signal": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "chart_summary": "2-3 sentence narrative summary"
}
"""


def _is_vision_model(model: str) -> bool:
    return any(model.startswith(p) for p in _VISION_PREFIXES)


class ChartVisionAgent:
    """
    Analyzes stock charts using either:
    - Vision LLM (image-based): when CHART_VISION_MODEL is set to a vision-capable model
    - Text LLM (description-based): fallback that works with any model (mistral, llama, etc.)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Use dedicated vision model if configured; otherwise fall back to risk model
        raw_model = settings.chart_vision_model or settings.risk_agent_model
        self._model = raw_model
        self._use_vision = _is_vision_model(raw_model)
        self._completion_kwargs = get_completion_kwargs(settings, raw_model)
        logger.info(
            "ChartVisionAgent initialized",
            extra={"model": self._model, "vision_mode": self._use_vision},
        )

    async def analyze(self, ticker: str) -> ChartAnalysis:
        ticker = ticker.upper().strip()
        logger.info("ChartVisionAgent starting", extra={"ticker": ticker})
        start = time.monotonic()

        try:
            df = await fetch_ohlcv(ticker)
        except Exception as exc:
            logger.warning("Failed to fetch chart data", extra={"ticker": ticker, "error": str(exc)})
            return self._fallback(ticker)

        messages: list[dict[str, Any]]

        if self._use_vision:
            try:
                chart_b64 = generate_chart_image(df, ticker)
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{chart_b64}"},
                            },
                            {
                                "type": "text",
                                "text": f"Analyze this {ticker} daily chart and return JSON as instructed.",
                            },
                        ],
                    },
                ]
            except Exception as exc:
                logger.warning("Chart image generation failed, falling back to text", extra={"error": str(exc)})
                self._use_vision = False

        if not self._use_vision:
            description = build_text_description(df, ticker)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Based on the following chart data for {ticker}, "
                        f"identify chart patterns and return JSON as instructed.\n\n{description}"
                    ),
                },
            ]

        try:
            response = await litellm.acompletion(
                model=self._model,
                max_tokens=1024,
                messages=messages,
                **self._completion_kwargs,
            )
            raw = response.choices[0].message.content or ""
            result = self._parse_response(raw, ticker)
            result.used_vision = self._use_vision
        except Exception as exc:
            logger.warning("Chart LLM call failed", extra={"ticker": ticker, "error": str(exc)})
            result = self._fallback(ticker)

        duration = time.monotonic() - start
        logger.info(
            "ChartVisionAgent complete",
            extra={
                "ticker": ticker,
                "signal": result.chart_signal,
                "trend": result.trend,
                "patterns": [p.name for p in result.patterns],
                "duration_s": round(duration, 2),
            },
        )
        return result

    def _parse_response(self, raw: str, ticker: str) -> ChartAnalysis:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        try:
            data = json.loads(text)
            patterns = [
                ChartPattern(
                    name=p.get("name", "Unknown"),
                    confidence=float(p.get("confidence", 0.5)),
                    implication=p.get("implication", "neutral"),
                )
                for p in data.get("patterns", [])
            ]
            return ChartAnalysis(
                ticker=ticker,
                trend=data.get("trend", "sideways"),
                trend_strength=data.get("trend_strength", "moderate"),
                patterns=patterns,
                support_levels=[float(x) for x in data.get("support_levels", [])],
                resistance_levels=[float(x) for x in data.get("resistance_levels", [])],
                chart_signal=data.get("chart_signal", "HOLD"),
                confidence=float(data.get("confidence", 0.5)),
                chart_summary=data.get("chart_summary", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to parse chart analysis JSON", extra={"error": str(exc), "raw": raw[:200]})
            return self._fallback(ticker)

    @staticmethod
    def _fallback(ticker: str) -> ChartAnalysis:
        return ChartAnalysis(
            ticker=ticker,
            trend="sideways",
            trend_strength="weak",
            chart_signal="HOLD",
            confidence=0.3,
            chart_summary="Chart analysis unavailable — insufficient data or model error.",
        )
