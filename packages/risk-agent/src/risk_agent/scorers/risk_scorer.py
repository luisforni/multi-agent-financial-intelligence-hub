from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


class RiskScorer:
    """Computes quantitative risk metrics from historical price data."""

    async def compute(self, ticker: str) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_compute, ticker)

    def _sync_compute(self, ticker: str) -> dict[str, Any]:
        try:
            import yfinance as yf

            hist = yf.Ticker(ticker).history(period="2y", interval="1d")
            if hist.empty or len(hist) < 60:
                return {"error": "Insufficient historical data"}

            returns = hist["Close"].pct_change().dropna()
            log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()

            # Annualized volatility
            vol_30d = float(returns.tail(30).std() * np.sqrt(_TRADING_DAYS))
            vol_90d = float(returns.tail(90).std() * np.sqrt(_TRADING_DAYS))

            # Value at Risk (parametric)
            mu = float(returns.mean())
            sigma = float(returns.std())
            var_95 = float(-(mu - 1.645 * sigma))
            var_99 = float(-(mu - 2.326 * sigma))

            # Expected Shortfall (CVaR) at 95%
            threshold = float(returns.quantile(0.05))
            es_95 = float(-returns[returns <= threshold].mean())

            # Beta vs S&P 500
            beta, market_corr = self._compute_beta(ticker, returns)

            # Sharpe ratio (annualized, risk-free = 5.25%)
            rf_daily = 0.0525 / _TRADING_DAYS
            excess = returns - rf_daily
            sharpe = float((excess.mean() / excess.std()) * np.sqrt(_TRADING_DAYS))

            # Sortino ratio
            downside = returns[returns < rf_daily]
            sortino = (
                float((excess.mean() / downside.std()) * np.sqrt(_TRADING_DAYS))
                if len(downside) > 0
                else 0.0
            )

            # Max drawdown
            cum = (1 + returns).cumprod()
            rolling_max = cum.cummax()
            drawdowns = (cum - rolling_max) / rolling_max
            max_dd = float(drawdowns.min())

            # Calmar ratio
            annual_ret = float(returns.mean() * _TRADING_DAYS)
            calmar = annual_ret / abs(max_dd) if max_dd != 0 else 0.0

            return {
                "historical_volatility_30d": round(vol_30d, 4),
                "historical_volatility_90d": round(vol_90d, 4),
                "value_at_risk_95": round(var_95, 4),
                "value_at_risk_99": round(var_99, 4),
                "expected_shortfall_95": round(es_95, 4),
                "beta": round(beta, 3) if beta is not None else None,
                "market_correlation": round(market_corr, 3) if market_corr is not None else None,
                "sharpe_ratio": round(sharpe, 3),
                "sortino_ratio": round(sortino, 3),
                "max_drawdown": round(max_dd, 4),
                "calmar_ratio": round(calmar, 3),
                "annualized_return": round(annual_ret, 4),
                "data_points": len(returns),
            }
        except Exception as exc:
            logger.exception("Risk computation failed", extra={"ticker": ticker})
            return {"error": str(exc)}

    def _compute_beta(
        self, ticker: str, stock_returns: pd.Series  # type: ignore[type-arg]
    ) -> tuple[float | None, float | None]:
        try:
            import yfinance as yf

            spy = yf.Ticker("SPY").history(period="2y", interval="1d")
            if spy.empty:
                return None, None
            spy_returns = spy["Close"].pct_change().dropna()

            aligned = pd.concat(
                [stock_returns.rename("stock"), spy_returns.rename("spy")], axis=1
            ).dropna()
            if len(aligned) < 30:
                return None, None

            cov_matrix = aligned.cov()
            beta = float(cov_matrix.loc["stock", "spy"] / cov_matrix.loc["spy", "spy"])
            corr = float(aligned.corr().loc["stock", "spy"])
            return beta, corr
        except Exception:
            return None, None
