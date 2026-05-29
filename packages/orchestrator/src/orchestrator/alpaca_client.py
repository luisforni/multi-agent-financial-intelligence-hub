from __future__ import annotations

import asyncio
import logging
import time
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
            raise ValueError(f"Quantity too small for order: {qty}")
        payload: dict[str, Any] = {
            "symbol": ticker,
            "qty": str(actual_qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with self._client() as c:
                    r = await c.post(f"{self._base_url}/v2/orders", json=payload)
                    if not r.is_success:
                        try:
                            body = r.json()
                            msg = body.get("message", r.text)
                        except Exception:
                            msg = r.text
                        raise httpx.HTTPStatusError(
                            f"HTTP {r.status_code}: {msg}",
                            request=r.request,
                            response=r,
                        )
                    data = r.json()
                    logger.info(
                        "Alpaca order submitted: %s %s x%.4f | id=%s status=%s",
                        side.upper(), ticker, qty, data.get("id"), data.get("status"),
                    )
                    return data
            except httpx.HTTPStatusError as e:
                # 4xx errors are client-side — retrying won't help
                if 400 <= e.response.status_code < 500:
                    raise
                last_exc = e
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
                last_exc = e
            if attempt < 2:
                wait = 2 ** attempt  # 1s, then 2s
                logger.warning(
                    "Alpaca order attempt %d/3 failed for %s — retrying in %ds",
                    attempt + 1, ticker, wait,
                )
                await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def get_order(self, order_id: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"{self._base_url}/v2/orders/{order_id}")
            r.raise_for_status()
            return r.json()

    async def wait_for_fill(self, order_id: str, timeout: float = 60.0) -> dict[str, Any]:
        """Poll an order until it reaches a terminal state (filled / canceled / rejected)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            order = await self.get_order(order_id)
            status = order.get("status", "")
            if status in ("filled", "partially_filled"):
                return order
            if status in ("canceled", "expired", "rejected", "done_for_day"):
                raise ValueError(f"Order {order_id} ended with status '{status}'")
            await asyncio.sleep(2.0)
        raise TimeoutError(f"Order {order_id} not filled within {timeout:.0f}s")

    async def close_position(self, ticker: str) -> dict[str, Any] | None:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with self._client() as c:
                    r = await c.delete(f"{self._base_url}/v2/positions/{ticker}")
                    if r.status_code == 404:
                        logger.warning("Alpaca: no open position for %s", ticker)
                        return None
                    if not r.is_success:
                        try:
                            body = r.json()
                            msg = body.get("message", r.text)
                        except Exception:
                            msg = r.text
                        raise httpx.HTTPStatusError(
                            f"HTTP {r.status_code}: {msg}",
                            request=r.request,
                            response=r,
                        )
                    logger.info("Alpaca position closed: %s", ticker)
                    return r.json()
            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise
                last_exc = e
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
                last_exc = e
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
        raise last_exc  # type: ignore[misc]

    async def close_all_positions(self) -> list[dict[str, Any]]:
        """Close all open positions using Alpaca's bulk endpoint."""
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
