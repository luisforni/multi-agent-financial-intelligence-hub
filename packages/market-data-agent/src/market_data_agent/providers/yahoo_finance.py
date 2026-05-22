from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.models import CompanyFundamentals, StockData, TechnicalIndicators

logger = logging.getLogger(__name__)


class YahooFinanceProvider:
    """Fetches real-time and historical market data from Yahoo Finance."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_stock_data(self, ticker: str) -> StockData:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_stock_data, ticker)

    def _fetch_stock_data(self, ticker: str) -> StockData:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        hist = yf_ticker.history(period="6mo", interval="1d", auto_adjust=True)

        if hist.empty:
            raise ValueError(f"No price data returned for {ticker}")

        current_price = float(info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1])
        prev_close = float(info.get("previousClose") or hist["Close"].iloc[-2] if len(hist) > 1 else current_price)

        technicals = self._compute_technicals(hist)
        fundamentals = self._extract_fundamentals(info)

        return StockData(
            ticker=ticker,
            company_name=info.get("longName") or info.get("shortName") or ticker,
            exchange=info.get("exchange"),
            currency=info.get("currency", "USD"),
            timestamp=datetime.utcnow(),
            current_price=current_price,
            open_price=float(info.get("open") or hist["Open"].iloc[-1]),
            high_price=float(info.get("dayHigh") or hist["High"].iloc[-1]),
            low_price=float(info.get("dayLow") or hist["Low"].iloc[-1]),
            previous_close=prev_close,
            price_change=round(current_price - prev_close, 4),
            price_change_pct=round((current_price - prev_close) / prev_close * 100, 4),
            volume=int(info.get("volume") or info.get("regularMarketVolume") or 0),
            average_volume=int(info.get("averageVolume") or 0),
            week_52_high=info.get("fiftyTwoWeekHigh"),
            week_52_low=info.get("fiftyTwoWeekLow"),
            technicals=technicals,
            fundamentals=fundamentals,
        )

    def _compute_technicals(self, hist: pd.DataFrame) -> TechnicalIndicators:
        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        return TechnicalIndicators(
            rsi_14=self._rsi(close, 14),
            macd=self._macd(close)[0],
            macd_signal=self._macd(close)[1],
            macd_histogram=self._macd(close)[2],
            bb_upper=self._bollinger_bands(close)[0],
            bb_middle=self._bollinger_bands(close)[1],
            bb_lower=self._bollinger_bands(close)[2],
            sma_20=self._sma(close, 20),
            sma_50=self._sma(close, 50),
            sma_200=self._sma(close, 200),
            ema_12=self._ema(close, 12),
            ema_26=self._ema(close, 26),
            adx=self._adx(high, low, close, 14),
            volume_sma_20=self._sma(volume, 20),
            atr_14=self._atr(high, low, close, 14),
        )

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> float | None:  # type: ignore[type-arg]
        if len(series) < period + 1:
            return None
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return float(val) if not np.isnan(val) else None

    @staticmethod
    def _sma(series: pd.Series, period: int) -> float | None:  # type: ignore[type-arg]
        if len(series) < period:
            return None
        val = series.rolling(period).mean().iloc[-1]
        return float(val) if not np.isnan(val) else None

    @staticmethod
    def _ema(series: pd.Series, period: int) -> float | None:  # type: ignore[type-arg]
        if len(series) < period:
            return None
        val = series.ewm(span=period, adjust=False).mean().iloc[-1]
        return float(val) if not np.isnan(val) else None

    @staticmethod
    def _macd(series: pd.Series) -> tuple[float | None, float | None, float | None]:  # type: ignore[type-arg]
        if len(series) < 26:
            return None, None, None
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        m = float(macd_line.iloc[-1])
        s = float(signal_line.iloc[-1])
        h = float(histogram.iloc[-1])
        return (
            m if not np.isnan(m) else None,
            s if not np.isnan(s) else None,
            h if not np.isnan(h) else None,
        )

    @staticmethod
    def _bollinger_bands(
        series: pd.Series, period: int = 20, std_dev: float = 2.0  # type: ignore[type-arg]
    ) -> tuple[float | None, float | None, float | None]:
        if len(series) < period:
            return None, None, None
        sma = series.rolling(period).mean()
        std = series.rolling(period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        u, m, l = float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])
        return (
            u if not np.isnan(u) else None,
            m if not np.isnan(m) else None,
            l if not np.isnan(l) else None,
        )

    @staticmethod
    def _adx(
        high: pd.Series,  # type: ignore[type-arg]
        low: pd.Series,  # type: ignore[type-arg]
        close: pd.Series,  # type: ignore[type-arg]
        period: int = 14,
    ) -> float | None:
        if len(close) < period * 2:
            return None
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        dm_plus = ((high - high.shift()) > (low.shift() - low)).astype(float) * (high - high.shift()).clip(lower=0)
        dm_minus = ((low.shift() - low) > (high - high.shift())).astype(float) * (low.shift() - low).clip(lower=0)
        atr = tr.rolling(period).mean()
        di_plus = 100 * dm_plus.rolling(period).mean() / atr.replace(0, np.nan)
        di_minus = 100 * dm_minus.rolling(period).mean() / atr.replace(0, np.nan)
        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
        adx = dx.rolling(period).mean()
        val = float(adx.iloc[-1])
        return val if not np.isnan(val) else None

    @staticmethod
    def _atr(
        high: pd.Series,  # type: ignore[type-arg]
        low: pd.Series,  # type: ignore[type-arg]
        close: pd.Series,  # type: ignore[type-arg]
        period: int = 14,
    ) -> float | None:
        if len(close) < period:
            return None
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        val = float(atr.iloc[-1])
        return val if not np.isnan(val) else None

    @staticmethod
    def _extract_fundamentals(info: dict) -> CompanyFundamentals:  # type: ignore[type-arg]
        def _safe(key: str) -> float | None:
            v = info.get(key)
            if v is None or v == "N/A":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return CompanyFundamentals(
            market_cap=_safe("marketCap"),
            pe_ratio=_safe("trailingPE"),
            forward_pe=_safe("forwardPE"),
            peg_ratio=_safe("pegRatio"),
            price_to_book=_safe("priceToBook"),
            price_to_sales=_safe("priceToSalesTrailing12Months"),
            ev_to_ebitda=_safe("enterpriseToEbitda"),
            eps_ttm=_safe("trailingEps"),
            eps_growth_yoy=_safe("earningsGrowth"),
            revenue_growth_yoy=_safe("revenueGrowth"),
            profit_margin=_safe("profitMargins"),
            debt_to_equity=_safe("debtToEquity"),
            current_ratio=_safe("currentRatio"),
            quick_ratio=_safe("quickRatio"),
            return_on_equity=_safe("returnOnEquity"),
            return_on_assets=_safe("returnOnAssets"),
            dividend_yield=_safe("dividendYield"),
            beta=_safe("beta"),
            shares_outstanding=_safe("sharesOutstanding"),
            float_shares=_safe("floatShares"),
            short_ratio=_safe("shortRatio"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )
