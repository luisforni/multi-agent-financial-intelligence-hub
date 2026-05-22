from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PortfolioAnalyzer:
    """Computes Kelly criterion position sizing and portfolio-level risk."""

    @staticmethod
    def kelly_criterion(
        win_probability: float,
        win_loss_ratio: float,
    ) -> float:
        """Full Kelly fraction. Use half-Kelly in practice for safety."""
        if win_loss_ratio <= 0 or win_probability <= 0 or win_probability >= 1:
            return 0.0
        kelly = win_probability - (1 - win_probability) / win_loss_ratio
        return max(0.0, min(kelly, 0.25))  # cap at 25% of portfolio

    @staticmethod
    def position_size_from_atr(
        portfolio_value: float,
        atr: float,
        current_price: float,
        risk_pct: float = 0.01,
    ) -> dict[str, float]:
        """Calculate position size based on ATR-based stop loss (1R risk)."""
        if atr <= 0 or current_price <= 0:
            return {"shares": 0.0, "notional": 0.0, "stop_loss": 0.0}
        stop_distance = 2.0 * atr
        dollar_risk = portfolio_value * risk_pct
        shares = dollar_risk / stop_distance
        notional = shares * current_price
        stop_loss = current_price - stop_distance
        return {
            "shares": round(shares, 2),
            "notional": round(notional, 2),
            "stop_loss": round(stop_loss, 2),
            "risk_per_share": round(stop_distance, 4),
            "portfolio_allocation_pct": round(notional / portfolio_value * 100, 2),
        }

    @staticmethod
    def compute_price_targets(
        current_price: float,
        atr: float,
        signal_direction: str,  # "bullish" | "bearish"
    ) -> dict[str, float]:
        if signal_direction == "bullish":
            return {
                "target_bull": round(current_price * 1.20, 2),
                "target_base": round(current_price * 1.10, 2),
                "target_bear": round(current_price * 1.03, 2),
                "stop_loss": round(current_price - 2 * atr, 2),
            }
        return {
            "target_bull": round(current_price * 0.97, 2),
            "target_base": round(current_price * 0.90, 2),
            "target_bear": round(current_price * 0.80, 2),
            "stop_loss": round(current_price + 2 * atr, 2),
        }
