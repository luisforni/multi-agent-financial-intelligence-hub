from __future__ import annotations

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

WATCHLIST_KEY = "fintelligence:watchlist"


class WatchlistManager:
    """Redis-backed set of tickers to monitor."""

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)

    async def add(self, ticker: str) -> bool:
        added = await self._redis.sadd(WATCHLIST_KEY, ticker.upper())
        logger.info("Watchlist add", extra={"ticker": ticker, "added": bool(added)})
        return bool(added)

    async def remove(self, ticker: str) -> bool:
        removed = await self._redis.srem(WATCHLIST_KEY, ticker.upper())
        logger.info("Watchlist remove", extra={"ticker": ticker, "removed": bool(removed)})
        return bool(removed)

    async def get_all(self) -> list[str]:
        members = await self._redis.smembers(WATCHLIST_KEY)
        return sorted(members)

    async def close(self) -> None:
        await self._redis.aclose()
