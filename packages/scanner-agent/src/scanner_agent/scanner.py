from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import yfinance as yf

from shared.models import ScannerAlert

from scanner_agent.signals import compute_score, detect_signals

logger = logging.getLogger(__name__)


class StockScanner:
    """
    Scans each ticker in the watchlist for technical signals.
    Publishes ScannerAlert to Redis when combined score exceeds threshold.
    """

    def __init__(self, redis_url: str, threshold: float = 0.5) -> None:
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._threshold = threshold

    async def scan_ticker(self, ticker: str) -> ScannerAlert | None:
        """Download data and evaluate signals for a single ticker. Returns alert if threshold met."""
        ticker = ticker.upper()
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).history(period="1y", interval="1d"),
            )
            if df.empty or len(df) < 20:
                logger.debug("Insufficient data", extra={"ticker": ticker})
                return None

            info = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).info or {},
            )
            company_name = info.get("longName") or info.get("shortName") or ticker
            current_price = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2])
            change_pct = (current_price - prev_close) / prev_close * 100 if prev_close else None

            signals = detect_signals(df)
            if not signals:
                return None

            score = compute_score(signals)
            if abs(score) < self._threshold:
                return None

            direction = "bullish" if score > 0 else "bearish"
            alert = ScannerAlert(
                ticker=ticker,
                company_name=company_name,
                current_price=current_price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                signals=signals,
                combined_score=round(score, 3),
                alert_direction=direction,
                timestamp=datetime.utcnow(),
            )
            logger.info(
                "Scanner alert generated",
                extra={
                    "ticker": ticker,
                    "direction": direction,
                    "score": score,
                    "signals": [s.signal_type for s in signals],
                },
            )
            return alert

        except Exception as exc:
            logger.warning("Scan failed", extra={"ticker": ticker, "error": str(exc)})
            return None

    async def publish_alert(self, alert: ScannerAlert) -> None:
        """Publish alert to Redis stream for orchestrator to consume."""
        payload = alert.model_dump(mode="json")
        await self._redis.xadd(
            "stream:scanner:alerts",
            {"data": json.dumps(payload)},
            maxlen=500,
        )
        logger.debug("Alert published to stream", extra={"ticker": alert.ticker})

    async def close(self) -> None:
        await self._redis.aclose()
