from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

import matplotlib
matplotlib.use("Agg")  # headless — no display needed

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Colour theme matching the frontend dark palette
_STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mpf.make_marketcolors(
        up="#00c896", down="#ff4d6d",
        wick={"up": "#00c896", "down": "#ff4d6d"},
        edge={"up": "#00c896", "down": "#ff4d6d"},
        volume={"up": "#00c896", "down": "#ff4d6d"},
    ),
    figcolor="#0f0f1a",
    gridcolor="#1e1e2e",
)


async def fetch_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(
        None,
        lambda: yf.Ticker(ticker).history(period=period, interval="1d"),
    )
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    df.index = pd.DatetimeIndex(df.index.date)  # type: ignore[assignment]
    return df


def generate_chart_image(df: pd.DataFrame, ticker: str) -> str:
    """
    Renders a candlestick chart with volume, 50-day and 200-day SMAs.
    Returns base64-encoded PNG string.
    """
    mav_periods: tuple[int, ...] = (50,)
    if len(df) >= 200:
        mav_periods = (50, 200)

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=_STYLE,
        volume=True,
        mav=mav_periods,
        title=f"\n{ticker} — 6-Month Daily Chart",
        figsize=(12, 7),
        returnfig=True,
        warn_too_much_data=10000,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="#0f0f1a")
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    plt.close(fig)
    return encoded


def build_text_description(df: pd.DataFrame, ticker: str) -> str:
    """
    Produces a rich text description of the chart for models that don't support vision.
    """
    close = df["Close"]
    volume = df["Volume"]
    price = float(close.iloc[-1])
    high = float(close.max())
    low = float(close.min())

    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    # Returns
    ret_1m = (price / float(close.iloc[-22]) - 1) * 100 if len(close) >= 22 else None
    ret_3m = (price / float(close.iloc[-66]) - 1) * 100 if len(close) >= 66 else None

    # Volume
    avg_vol = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else None
    curr_vol = float(volume.iloc[-1])
    vol_ratio = curr_vol / avg_vol if avg_vol else None

    lines = [
        f"STOCK CHART ANALYSIS — {ticker}",
        f"Period: last {len(df)} trading days (daily candles)",
        "",
        "PRICE ACTION:",
        f"  Current price:  ${price:.2f}",
        f"  Range (period): ${low:.2f} – ${high:.2f}",
    ]
    if ret_1m is not None:
        lines.append(f"  1-month return:  {ret_1m:+.1f}%")
    if ret_3m is not None:
        lines.append(f"  3-month return:  {ret_3m:+.1f}%")

    lines.append("")
    lines.append("MOVING AVERAGES:")
    if sma50:
        pct50 = (price / sma50 - 1) * 100
        lines.append(f"  50-day SMA:  ${sma50:.2f}  (price is {pct50:+.1f}% vs SMA50)")
    if sma200:
        pct200 = (price / sma200 - 1) * 100
        lines.append(f"  200-day SMA: ${sma200:.2f}  (price is {pct200:+.1f}% vs SMA200)")
    if sma50 and sma200:
        cross = "ABOVE" if sma50 > sma200 else "BELOW"
        lines.append(f"  50-day SMA is {cross} 200-day SMA")

    lines.append("")
    lines.append("VOLUME:")
    if vol_ratio:
        lines.append(f"  Today's volume is {vol_ratio:.1f}x the 20-day average")

    # Recent candle pattern (last 5 days)
    lines.append("")
    lines.append("LAST 5 CANDLES:")
    for i in range(-5, 0):
        row = df.iloc[i]
        direction = "▲" if float(row["Close"]) >= float(row["Open"]) else "▼"
        lines.append(
            f"  {df.index[i]}  {direction}  O:{row['Open']:.2f}  H:{row['High']:.2f}"
            f"  L:{row['Low']:.2f}  C:{row['Close']:.2f}"
        )

    return "\n".join(lines)
