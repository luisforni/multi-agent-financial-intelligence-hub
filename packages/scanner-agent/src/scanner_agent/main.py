from __future__ import annotations

import asyncio
import logging
import os
import signal

from shared.config import get_settings
from shared.logging import configure_logging

from scanner_agent.scanner import StockScanner
from scanner_agent.watchlist import WatchlistManager

logger = logging.getLogger(__name__)

_shutdown = asyncio.Event()


def _handle_signal(*_: object) -> None:
    _shutdown.set()


async def scan_loop(scanner: StockScanner, watchlist: WatchlistManager, interval: int) -> None:
    logger.info("Scanner loop started", extra={"interval_s": interval})
    while not _shutdown.is_set():
        tickers = await watchlist.get_all()
        if tickers:
            logger.info("Scanning watchlist", extra={"tickers": tickers, "count": len(tickers)})
            tasks = [scanner.scan_ticker(t) for t in tickers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Scan task error", extra={"error": str(result)})
                elif result is not None:
                    await scanner.publish_alert(result)
        else:
            logger.debug("Watchlist empty — nothing to scan")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=float(interval))
        except asyncio.TimeoutError:
            pass


DEFAULT_WATCHLIST = [
    # Magnificent 7
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
    # Semiconductors
    "AMD", "INTC", "AVGO", "QCOM", "MU", "TSM",
    # Finance
    "JPM", "GS", "BAC", "MS", "BLK", "V", "MA",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "LLY",
    # Energy
    "XOM", "CVX", "COP",
    # Consumer & Retail
    "WMT", "PG", "KO", "MCD", "SBUX", "NKE",
    # Industrials & Others
    "BA", "CAT", "GE", "HON",
    # Crypto-related
    "COIN", "MSTR",
    # Broad ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Sector ETFs
    "GLD", "TLT", "XLK", "XLF", "XLE",
]


async def seed_default_watchlist(watchlist: WatchlistManager) -> None:
    existing = set(await watchlist.get_all())
    missing = [t for t in DEFAULT_WATCHLIST if t not in existing]
    if not missing:
        logger.info("Default watchlist already complete", extra={"count": len(existing)})
        return
    for ticker in missing:
        await watchlist.add(ticker)
    logger.info("Seeded watchlist with missing defaults", extra={"added": len(missing), "total": len(existing) + len(missing)})


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    scanner = StockScanner(
        redis_url=settings.redis_url,
        threshold=settings.scanner_signal_threshold,
    )
    watchlist = WatchlistManager(redis_url=settings.redis_url)

    logger.info("Scanner Agent starting")
    await seed_default_watchlist(watchlist)
    try:
        await scan_loop(scanner, watchlist, settings.scanner_interval_seconds)
    finally:
        await scanner.close()
        await watchlist.close()
    logger.info("Scanner Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
