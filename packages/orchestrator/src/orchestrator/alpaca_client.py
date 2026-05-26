from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.config import Settings

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Thin async wrapper around the Alpaca Trading REST API v2."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.alpaca_base_url.rstrip("/")
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            "Content-Type": "application/json",
        }
        self._mode = settings.alpaca_mode

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self._headers, timeout=15.0)

    async def get_account(self) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"{self._base_url}/v2/account")
            r.raise_for_status()
            return r.json()

    async def submit_order(
        self,
        ticker: str,
        qty: float,
        side: str,          # "buy" | "sell"
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        # Alpaca does not support fractional quantities for short (sell) orders
        actual_qty = int(qty) if side == "sell" else round(qty, 4)
        if actual_qty <= 0:
            raise ValueError(f"Quantity too small for short order: {qty}")
        payload: dict[str, Any] = {
            "symbol": ticker,
            "qty": str(actual_qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        async with self._client() as c:
            r = await c.post(f"{self._base_url}/v2/orders", json=payload)
            r.raise_for_status()
            data = r.json()
            logger.info(
                "Alpaca order submitted: %s %s x%.4f | id=%s status=%s",
                side.upper(), ticker, qty, data.get("id"), data.get("status"),
            )
            return data

    async def close_position(self, ticker: str) -> dict[str, Any] | None:
        async with self._client() as c:
            r = await c.delete(
                f"{self._base_url}/v2/positions/{ticker}",
                params={"qty": None},
            )
            if r.status_code == 404:
                logger.warning("Alpaca: no open position for %s", ticker)
                return None
            r.raise_for_status()
            data = r.json()
            logger.info("Alpaca position closed: %s", ticker)
            return data

    async def close_all_positions(self) -> list[dict[str, Any]]:
        """Close all open positions using Alpaca's bulk endpoint. Works during and after market hours."""
        async with self._client() as c:
            r = await c.delete(
                f"{self._base_url}/v2/positions",
                params={"cancel_orders": "true"},
            )
            if r.status_code == 207:
                results = r.json()
                for item in results:
                    symbol = item.get("symbol", "?")
                    status = item.get("status", "?")
                    logger.info("Alpaca bulk close: %s → %s", symbol, status)
                return results
            r.raise_for_status()
            return r.json()

    async def get_positions(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get(f"{self._base_url}/v2/positions")
            r.raise_for_status()
            return r.json()

    async def get_orders(self, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get(
                f"{self._base_url}/v2/orders",
                params={"status": status, "limit": limit, "direction": "desc"},
            )
            r.raise_for_status()
            return r.json()
