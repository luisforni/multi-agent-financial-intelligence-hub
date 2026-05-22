from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from shared.models import TechnicalSignal

logger = logging.getLogger(__name__)


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


def _macd(close: pd.Series) -> tuple[float, float]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1])


def _bollinger(close: pd.Series, period: int = 20) -> tuple[float, float, float]:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])


def detect_signals(df: pd.DataFrame) -> list[TechnicalSignal]:
    """
    Runs all technical signal detectors on OHLCV DataFrame.
    Returns a list of TechnicalSignal objects for signals that are firing.
    """
    if len(df) < 30:
        return []

    close = df["Close"]
    volume = df["Volume"]
    signals: list[TechnicalSignal] = []

    # ── RSI ──────────────────────────────────────────────────────────
    rsi = _rsi(close)
    if rsi < 30:
        signals.append(TechnicalSignal(
            signal_type="RSI_OVERSOLD",
            direction="bullish",
            strength=min(1.0, (30 - rsi) / 15),
            description=f"RSI at {rsi:.1f} — oversold territory (< 30)",
        ))
    elif rsi > 70:
        signals.append(TechnicalSignal(
            signal_type="RSI_OVERBOUGHT",
            direction="bearish",
            strength=min(1.0, (rsi - 70) / 15),
            description=f"RSI at {rsi:.1f} — overbought territory (> 70)",
        ))

    # ── MACD crossover (last 3 candles) ─────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line

    if len(hist) >= 3:
        prev_hist = float(hist.iloc[-2])
        curr_hist = float(hist.iloc[-1])
        if prev_hist < 0 < curr_hist:
            signals.append(TechnicalSignal(
                signal_type="MACD_BULLISH_CROSS",
                direction="bullish",
                strength=min(1.0, abs(curr_hist) / (abs(float(close.iloc[-1])) * 0.005 + 1e-9)),
                description="MACD line crossed above signal line (bullish momentum)",
            ))
        elif prev_hist > 0 > curr_hist:
            signals.append(TechnicalSignal(
                signal_type="MACD_BEARISH_CROSS",
                direction="bearish",
                strength=min(1.0, abs(curr_hist) / (abs(float(close.iloc[-1])) * 0.005 + 1e-9)),
                description="MACD line crossed below signal line (bearish momentum)",
            ))

    # ── Bollinger Band breakout ──────────────────────────────────────
    if len(close) >= 20:
        bb_upper, bb_mid, bb_lower = _bollinger(close)
        price = float(close.iloc[-1])
        band_width = bb_upper - bb_lower
        if band_width > 0:
            if price <= bb_lower:
                signals.append(TechnicalSignal(
                    signal_type="BB_LOWER_TOUCH",
                    direction="bullish",
                    strength=min(1.0, (bb_lower - price) / (band_width * 0.1) + 0.5),
                    description=f"Price ${price:.2f} at/below lower Bollinger Band (${bb_lower:.2f})",
                ))
            elif price >= bb_upper:
                signals.append(TechnicalSignal(
                    signal_type="BB_UPPER_TOUCH",
                    direction="bearish",
                    strength=min(1.0, (price - bb_upper) / (band_width * 0.1) + 0.5),
                    description=f"Price ${price:.2f} at/above upper Bollinger Band (${bb_upper:.2f})",
                ))

    # ── Volume spike ─────────────────────────────────────────────────
    if len(volume) >= 20:
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        if avg_vol > 0 and curr_vol > avg_vol * 1.5:
            ratio = curr_vol / avg_vol
            # Direction from price change
            price_change = float(close.iloc[-1]) - float(close.iloc[-2])
            direction = "bullish" if price_change >= 0 else "bearish"
            signals.append(TechnicalSignal(
                signal_type="VOLUME_SPIKE",
                direction=direction,
                strength=min(1.0, (ratio - 1.5) / 2.0 + 0.5),
                description=f"Volume {ratio:.1f}x above 20-day average",
            ))

    # ── Golden / Death cross (last 5 candles) ────────────────────────
    if len(close) >= 200:
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        diff = sma50 - sma200
        if len(diff.dropna()) >= 5:
            prev5 = float(diff.iloc[-5])
            curr = float(diff.iloc[-1])
            if prev5 < 0 < curr:
                signals.append(TechnicalSignal(
                    signal_type="GOLDEN_CROSS",
                    direction="bullish",
                    strength=0.85,
                    description="50-day SMA crossed above 200-day SMA (golden cross)",
                ))
            elif prev5 > 0 > curr:
                signals.append(TechnicalSignal(
                    signal_type="DEATH_CROSS",
                    direction="bearish",
                    strength=0.85,
                    description="50-day SMA crossed below 200-day SMA (death cross)",
                ))

    # ── 52-week high/low proximity ───────────────────────────────────
    high_52w = float(close.rolling(252).max().iloc[-1]) if len(close) >= 252 else float(close.max())
    low_52w = float(close.rolling(252).min().iloc[-1]) if len(close) >= 252 else float(close.min())
    price = float(close.iloc[-1])

    if high_52w > 0 and abs(price - high_52w) / high_52w < 0.02:
        signals.append(TechnicalSignal(
            signal_type="NEAR_52W_HIGH",
            direction="bearish",
            strength=0.6,
            description=f"Price within 2% of 52-week high (${high_52w:.2f})",
        ))
    elif low_52w > 0 and abs(price - low_52w) / low_52w < 0.02:
        signals.append(TechnicalSignal(
            signal_type="NEAR_52W_LOW",
            direction="bullish",
            strength=0.6,
            description=f"Price within 2% of 52-week low (${low_52w:.2f})",
        ))

    return signals


def compute_score(signals: list[TechnicalSignal]) -> float:
    """Returns combined score: -1.0 (strong sell) to +1.0 (strong buy)."""
    if not signals:
        return 0.0
    total = sum(
        s.strength * (1.0 if s.direction == "bullish" else -1.0)
        for s in signals
    )
    return max(-1.0, min(1.0, total / max(len(signals), 1)))
