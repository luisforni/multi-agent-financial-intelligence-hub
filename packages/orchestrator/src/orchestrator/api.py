from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
import yfinance as yf
from fastapi import FastAPI, HTTPException, Path, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from shared.logging import configure_logging
from shared.message_bus import MessageBus
from shared.models import (
    ClosedTrade,
    InvestmentRecommendation,
    Position,
    ScannerAlert,
    SentimentData,
    Signal,
    TradeDirection,
)

from orchestrator.alpaca_client import AlpacaClient
from orchestrator.coordinator import AgentCoordinator
from orchestrator.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

_coordinator: AgentCoordinator | None = None
_message_bus: MessageBus | None = None
_redis: aioredis.Redis | None = None
_alpaca: AlpacaClient | None = None

# Cached Alpaca account state — refreshed on every sync
_alpaca_buying_power: float = 0.0
_alpaca_shorting_enabled: bool = True

_recent_analyses: deque[dict[str, Any]] = deque(maxlen=50)

# Analysis dedup: ticker → epoch seconds of last triggered analysis
_last_analysis_time: dict[str, float] = {}
ANALYSIS_COOLDOWN_SECONDS = 1800  # 30 minutes

# Active analysis tasks: ticker → asyncio.Task (for cancellation)
_active_tasks: dict[str, asyncio.Task[None]] = {}

# PDT conviction thresholds: minimum confidence required to open a position.
# As the weekly day-trade budget shrinks, the bar rises to protect the remaining slots
# from low-probability setups (which are more likely to hit stop-loss same day).
_PDT_CONFIDENCE_NORMAL = 0.60    # ≥2 slots remaining: standard signal quality
_PDT_CONFIDENCE_CAUTIOUS = 0.75  # 1 slot remaining: require strong conviction

# Circuit breaker: consecutive LLM failures → pause scanner auto-analysis
_consecutive_llm_failures = 0
_LLM_FAILURE_THRESHOLD = 3   # pause after this many back-to-back failures
_llm_paused_until: float = 0.0
_LLM_PAUSE_SECONDS = 300     # 5-minute pause before retrying

# Queue 1 — slow: background sentiment refresh (1 at a time, 24/7)
_sentiment_queue: asyncio.Queue[str] = asyncio.Queue()
_sentiment_queued: set[str] = set()  # dedup

# Queue 2 — fast: scanner-triggered analyses (1 at a time, NEVER runs sentiment)
_scan_queue: asyncio.Queue[str] = asyncio.Queue()
_scan_queued: set[str] = set()  # dedup: avoid queuing the same ticker twice

# Scanner scores per ticker (updated on every alert, used to prioritise overnight queue)
_scanner_scores: dict[str, float] = {}

# Sentiment cache: ticker → (SentimentData, unix timestamp)
# Valid for SENTIMENT_CACHE_TTL seconds; used as fast-path input during market hours
_sentiment_cache: dict[str, tuple[SentimentData, float]] = {}
SENTIMENT_CACHE_TTL = 86400        # 24 h — covers overnight + full trading day
OVERNIGHT_TICKER_COOLDOWN = 21600  # 6 h — minimum gap between overnight re-analyses
SENTIMENT_CACHE_KEY = "fintelligence:sentiment_cache"

ANALYSES_KEY = "fintelligence:analyses"

# Paper portfolio (in-memory; Redis-backed for persistence)
_positions: dict[str, Position] = {}     # ticker → open position
_closed_trades: deque[ClosedTrade] = deque(maxlen=200)

# Dynamic position sizing state
_peak_equity: float = 0.0               # highest equity reached (for drawdown calc)
_trading_paused: bool = False           # paused due to drawdown

# Trading safeguards state
_day_trade_log: list[Any] = []           # datetime.date entries for each day trade
_unsettled: list[tuple[Any, float]] = [] # (settle_date, amount) for T+2 settlement

WATCHLIST_KEY = "fintelligence:watchlist"
PORTFOLIO_KEY = "fintelligence:portfolio"
CLOSED_TRADES_KEY = "fintelligence:closed_trades"


# ── Sentiment cache ───────────────────────────────────────────────────────────

async def _save_sentiment_cache(ticker: str, sentiment: SentimentData) -> None:
    ts = time.time()
    _sentiment_cache[ticker] = (sentiment, ts)
    if _redis:
        blob = json.dumps({"data": json.loads(sentiment.model_dump_json()), "ts": ts})
        await _redis.hset(SENTIMENT_CACHE_KEY, ticker, blob)


def _get_cached_sentiment(ticker: str) -> SentimentData | None:
    entry = _sentiment_cache.get(ticker)
    if entry is None:
        return None
    sentiment, ts = entry
    if time.time() - ts > SENTIMENT_CACHE_TTL:
        _sentiment_cache.pop(ticker, None)
        return None
    return sentiment


async def _load_sentiment_cache_from_redis() -> None:
    if not _redis:
        return
    raw = await _redis.hgetall(SENTIMENT_CACHE_KEY)
    now = time.time()
    loaded = 0
    for ticker, blob in raw.items():
        try:
            obj = json.loads(blob)
            if now - obj["ts"] < SENTIMENT_CACHE_TTL:
                _sentiment_cache[ticker] = (SentimentData.model_validate(obj["data"]), obj["ts"])
                loaded += 1
        except Exception:
            pass
    logger.info("Sentiment cache loaded from Redis: %d valid entries", loaded)


def _neutral_sentiment(ticker: str) -> SentimentData:
    """Neutral placeholder used when no cached sentiment exists for a ticker."""
    from shared.models import SentimentLabel
    return SentimentData(
        ticker=ticker,
        company_name=ticker,
        label=SentimentLabel.NEUTRAL,
        overall_score=0.0,
        sentiment_summary="Sentiment not yet available — analysis based on market data and chart only.",
    )


async def _enqueue_sentiment_warmup() -> None:
    """Queue all watchlist tickers that lack a fresh sentiment entry (highest scanner score first)."""
    if not _redis:
        return
    try:
        tickers = list(await _redis.smembers(WATCHLIST_KEY))
        tickers.sort(key=lambda t: _scanner_scores.get(t, 0.0), reverse=True)
        queued = 0
        for ticker in tickers:
            if ticker not in _sentiment_queued and _get_cached_sentiment(ticker) is None:
                _sentiment_queued.add(ticker)
                await _sentiment_queue.put(ticker)
                queued += 1
        if queued:
            logger.info("Sentiment warmup: queued %d tickers with missing/stale cache", queued)
    except Exception as exc:
        logger.warning("Sentiment warmup failed: %s", exc)


async def _sentiment_worker() -> None:
    """
    Queue 1 — slow, 24/7 background task.
    Refreshes the sentiment cache for every watchlist ticker one at a time.
    Yields to Queue 2 (scanner): waits until no active LLM analyses are running
    before starting a sentiment call, so both queues never share Ollama simultaneously.
    """
    await asyncio.sleep(15)  # let startup settle before first run
    await _enqueue_sentiment_warmup()
    try:
        while True:
            try:
                # Wait up to 30 min for the next ticker; if queue is empty, re-enqueue stale ones
                ticker = await asyncio.wait_for(_sentiment_queue.get(), timeout=1800)
            except asyncio.TimeoutError:
                await _enqueue_sentiment_warmup()
                continue

            _sentiment_queued.discard(ticker)
            if not _coordinator:
                _sentiment_queue.task_done()
                continue

            # During market hours Ollama is reserved exclusively for the scanner.
            # Wait until market closes before running any sentiment LLM call.
            if _is_market_open():
                logger.debug("Sentiment worker paused — market open, Ollama reserved for scanner")
                _sentiment_queued.add(ticker)
                await _sentiment_queue.put(ticker)
                _sentiment_queue.task_done()
                await asyncio.sleep(300)  # check again in 5 min
                continue

            try:
                logger.info("Sentiment worker: refreshing %s", ticker)
                result = await _coordinator.refresh_sentiment(ticker)
                await _save_sentiment_cache(ticker, result)
                logger.info(
                    "Sentiment worker: cached %s → %s (score %+.2f)",
                    ticker, result.label, result.overall_score or 0.0,
                )
            except Exception as exc:
                logger.warning("Sentiment worker: %s failed — %s", ticker, exc)
            finally:
                _sentiment_queue.task_done()

            await asyncio.sleep(5)  # brief pause between tickers
    except asyncio.CancelledError:
        pass


# ── Overnight batch analyzer ──────────────────────────────────────────────────

async def _overnight_analyzer() -> None:
    """
    While the market is closed, run full analysis (including sentiment) for every
    watchlist ticker ordered by latest scanner score.  Results are stored in the
    sentiment cache so that market-hours analyses can skip the slow LLM sentiment
    call and use pre-computed data instead.
    """
    try:
        while True:
            if _is_market_open():
                await asyncio.sleep(60)
                continue

            if not _redis or not _coordinator:
                await asyncio.sleep(600)
                continue

            tickers = list(await _redis.smembers(WATCHLIST_KEY))
            if not tickers:
                await asyncio.sleep(600)
                continue

            # Sort highest scanner score first (most likely to trigger at open)
            tickers.sort(key=lambda t: _scanner_scores.get(t, 0.0), reverse=True)

            to_analyze = [
                t for t in tickers
                if time.monotonic() - _last_analysis_time.get(t, 0) >= OVERNIGHT_TICKER_COOLDOWN
                and t not in _scan_queued
                and t not in _active_tasks
            ][:10]  # limit to top-10 by scanner score to conserve cloud LLM quota

            if not to_analyze:
                await asyncio.sleep(1800)  # all tickers fresh — check again in 30 min
                continue

            logger.info(
                "Overnight analysis: queuing %d tickers (top: %s)",
                len(to_analyze),
                ", ".join(f"{t}({_scanner_scores.get(t, 0):.2f})" for t in to_analyze[:5]),
            )

            for ticker in to_analyze:
                if _is_market_open():
                    logger.info("Market opened — stopping overnight batch")
                    break
                if ticker not in _scan_queued and ticker not in _active_tasks:
                    _scan_queued.add(ticker)
                    _last_analysis_time[ticker] = time.monotonic()
                    await _scan_queue.put(ticker)

            # Wait for the queued batch to finish before sleeping
            await _scan_queue.join()
            logger.info("Overnight analysis pass complete")
            await asyncio.sleep(1800)

    except asyncio.CancelledError:
        pass


# ── Alpaca sync ───────────────────────────────────────────────────────────────

async def _sync_with_alpaca() -> None:
    """Reconcile in-memory positions against Alpaca and refresh cached account state."""
    global _alpaca_buying_power, _alpaca_shorting_enabled
    if not _alpaca:
        return
    try:
        # Refresh account state so position sizing and SHORT guard use fresh data
        account = await _alpaca.get_account()
        _alpaca_buying_power = float(
            account.get("non_marginable_buying_power") or account.get("buying_power") or 0
        )
        _alpaca_shorting_enabled = account.get("shorting_enabled", True)
        if not _alpaca_shorting_enabled:
            logger.info("Alpaca shorting disabled — SHORT signals will be skipped")

        alpaca_positions = await _alpaca.get_positions()
        alpaca_tickers = {p["symbol"] for p in alpaca_positions}

        # Remove app positions absent from Alpaca (phantom / rejected orders)
        for ticker in list(_positions.keys()):
            if ticker not in alpaca_tickers:
                logger.warning("Removing phantom position %s (not found in Alpaca)", ticker)
                _positions.pop(ticker, None)
                await _delete_position(ticker)

        # Import Alpaca positions the app doesn't know about
        for p in alpaca_positions:
            ticker = p["symbol"]
            if ticker not in _positions:
                direction = TradeDirection.LONG if p["side"] == "long" else TradeDirection.SHORT
                pos = Position(
                    ticker=ticker,
                    company_name=ticker,
                    direction=direction,
                    entry_price=float(p["avg_entry_price"]),
                    quantity=float(p["qty"]),
                    current_price=float(p["current_price"]),
                    signal=Signal.BUY if direction == TradeDirection.LONG else Signal.SELL,
                )
                _positions[ticker] = pos
                await _save_position(pos)
                logger.info("Imported Alpaca position %s @ $%.2f", ticker, pos.entry_price)

        logger.info(
            "Alpaca sync complete — app has %d positions, Alpaca has %d",
            len(_positions), len(alpaca_tickers),
        )
    except Exception as exc:
        logger.warning("Alpaca sync failed (non-fatal): %s", exc)


# ── Scanner FIFO queue worker ─────────────────────────────────────────────────

async def _periodic_reconcile() -> None:
    """Sync internal positions against Alpaca every 5 minutes."""
    await asyncio.sleep(60)  # initial delay — let startup settle first
    while True:
        try:
            await _sync_with_alpaca()
        except Exception as exc:
            logger.warning("Periodic reconciliation failed: %s", exc)
        await asyncio.sleep(300)


async def _verify_fill(ticker: str, order_id: str, direction: str) -> None:
    """Background task: confirm an Alpaca order was filled and notify the frontend."""
    if not _alpaca:
        return
    try:
        order = await _alpaca.wait_for_fill(order_id)
        filled_qty = float(order.get("filled_qty") or 0)
        fill_price = float(order.get("filled_avg_price") or 0)
        logger.info(
            "Alpaca fill confirmed: %s %s %.4f @ $%.4f",
            direction, ticker, filled_qty, fill_price,
        )
        await ws_manager.broadcast({
            "type": "alpaca_order_filled",
            "ticker": ticker,
            "direction": direction,
            "qty": filled_qty,
            "price": fill_price,
        })
    except Exception as exc:
        logger.warning("Alpaca fill not confirmed for %s: %s", ticker, exc)
        await ws_manager.broadcast({
            "type": "alpaca_order_failed",
            "ticker": ticker,
            "message": f"Fill not confirmed: {exc}",
        })


async def _scan_queue_worker() -> None:
    """Process scanner-triggered analyses one at a time to avoid Ollama overload."""
    try:
        while True:
            ticker = await _scan_queue.get()
            _scan_queued.discard(ticker)
            try:
                await _auto_analyze(ticker)
            except Exception:
                pass
            finally:
                _scan_queue.task_done()
            # Overnight: throttle to 1 analysis/90s to stay within Groq 12K TPM free tier
            # (Risk Agent uses ~10K tokens/request; 90s gap ensures we never exceed the limit)
            if not _is_market_open():
                await asyncio.sleep(90)
    except asyncio.CancelledError:
        pass


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _coordinator, _message_bus, _redis, _alpaca

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        logger.info("Redis connected")
        await _load_portfolio_from_redis()
        await _load_analyses_from_redis()
        await _load_sentiment_cache_from_redis()
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        _redis = None

    _message_bus = MessageBus(settings.redis_url)
    try:
        await _message_bus.connect()
    except Exception as exc:
        logger.warning("Message bus unavailable: %s", exc)
        _message_bus = None

    _coordinator = AgentCoordinator(settings, message_bus=_message_bus)

    if settings.alpaca_enabled:
        _alpaca = AlpacaClient(settings)
        logger.info("Alpaca trading enabled (mode=%s)", settings.alpaca_mode)
        await _sync_with_alpaca()
    else:
        logger.info("Alpaca trading disabled (ALPACA_MODE not set or keys missing)")

    logger.info("Financial Intelligence Hub API started")

    scanner_task = asyncio.create_task(_scanner_listener(settings.redis_url))
    price_task = asyncio.create_task(_price_monitor())
    queue_task = asyncio.create_task(_scan_queue_worker())
    overnight_task = asyncio.create_task(_overnight_analyzer())
    reconcile_task = asyncio.create_task(_periodic_reconcile())
    sentiment_task = asyncio.create_task(_sentiment_worker())

    yield

    scanner_task.cancel()
    price_task.cancel()
    queue_task.cancel()
    overnight_task.cancel()
    reconcile_task.cancel()
    sentiment_task.cancel()
    if _coordinator:
        await _coordinator.close()
    if _message_bus:
        await _message_bus.disconnect()
    if _redis:
        await _redis.aclose()


# ── Portfolio persistence ─────────────────────────────────────────────────────

async def _load_portfolio_from_redis() -> None:
    if not _redis:
        return
    raw = await _redis.hgetall(PORTFOLIO_KEY)
    for ticker, data in raw.items():
        try:
            _positions[ticker] = Position(**json.loads(data))
        except Exception:
            pass
    raw_closed = await _redis.lrange(CLOSED_TRADES_KEY, 0, 199)
    for item in raw_closed:
        try:
            _closed_trades.append(ClosedTrade(**json.loads(item)))
        except Exception:
            pass
    logger.info("Portfolio loaded from Redis: %d open positions", len(_positions))


async def _load_analyses_from_redis() -> None:
    if not _redis:
        return
    raw = await _redis.lrange(ANALYSES_KEY, 0, 49)
    for item in raw:
        try:
            _recent_analyses.append(json.loads(item))
        except Exception:
            pass
    logger.info("Analyses loaded from Redis: %d entries", len(_recent_analyses))


async def _save_analysis_to_redis(summary: dict[str, Any]) -> None:
    if _redis:
        await _redis.lpush(ANALYSES_KEY, json.dumps(summary, default=str))
        await _redis.ltrim(ANALYSES_KEY, 0, 49)


async def _save_position(pos: Position) -> None:
    if _redis:
        await _redis.hset(PORTFOLIO_KEY, pos.ticker, pos.model_dump_json())


async def _delete_position(ticker: str) -> None:
    if _redis:
        await _redis.hdel(PORTFOLIO_KEY, ticker)


async def _save_closed_trade(trade: ClosedTrade) -> None:
    if _redis:
        await _redis.lpush(CLOSED_TRADES_KEY, trade.model_dump_json())
        await _redis.ltrim(CLOSED_TRADES_KEY, 0, 199)


# ── Dynamic position sizing ───────────────────────────────────────────────────

def _current_equity(settings: Any) -> float:
    realized = sum(t.realized_pnl for t in _closed_trades)
    unrealized = sum(p.unrealized_pnl() or 0.0 for p in _positions.values())
    return settings.initial_balance + realized + unrealized


def _compute_position_size(settings: Any) -> float:
    equity = _current_equity(settings)
    # Fixed 1/max_positions_cap allocation so every position gets an equal slice.
    # Using positions+1 as denominator caused first positions to take 50-100% of equity,
    # exhausting Alpaca buying power and leaving cents for later positions.
    return max(settings.min_position_usd, equity / settings.max_positions_cap)


def _max_positions_allowed(settings: Any) -> int:
    equity = _current_equity(settings)
    dynamic = int(equity / settings.min_position_usd)
    return min(dynamic, settings.max_positions_cap)


def _check_drawdown(settings: Any) -> bool:
    global _peak_equity, _trading_paused
    equity = _current_equity(settings)
    if equity > _peak_equity:
        _peak_equity = equity
        if _trading_paused:
            _trading_paused = False
            logger.info("Drawdown recovered — trading resumed (equity=%.2f)", equity)
    if _peak_equity > 0:
        drawdown = (_peak_equity - equity) / _peak_equity
        if drawdown >= settings.max_drawdown_pct and not _trading_paused:
            _trading_paused = True
            logger.warning(
                "Drawdown %.1f%% >= %.1f%% — trading PAUSED (equity=%.2f peak=%.2f)",
                drawdown * 100, settings.max_drawdown_pct * 100, equity, _peak_equity,
            )
    return _trading_paused


def _is_market_open() -> bool:
    from datetime import timezone
    now = datetime.now(timezone.utc)
    # NYSE: Mon–Fri 13:30–20:00 UTC
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=13, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=20, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


# ── Trading safeguards helpers ────────────────────────────────────────────────

def _slippage_price(price: float, direction: TradeDirection, is_opening: bool, settings: Any) -> float:
    """Simulate bid/ask spread: buys pay more, sells receive less."""
    pct = settings.slippage_pct
    buying = (direction == TradeDirection.LONG and is_opening) or \
             (direction == TradeDirection.SHORT and not is_opening)
    return round(price * (1 + pct if buying else 1 - pct), 4)


def _day_trades_in_window() -> int:
    """Count day trades recorded in the last ~5 business days (7 calendar days)."""
    from datetime import date as _date, timedelta
    cutoff = _date.today() - timedelta(days=7)
    return sum(1 for d in _day_trade_log if d >= cutoff)


def _unsettled_amount() -> float:
    """Return total cash pending T+2 settlement; prune expired entries in-place."""
    from datetime import date as _date
    today = _date.today()
    active = [(s, a) for s, a in _unsettled if s > today]
    _unsettled[:] = active
    return sum(a for _, a in active)


def _can_close_today(pos: Position, settings: Any) -> bool:
    """False if closing this position today would create a PDT day-trade."""
    if settings.min_hold_days <= 0:
        return True
    from datetime import timezone
    ent = pos.entry_time if pos.entry_time.tzinfo else pos.entry_time.replace(tzinfo=timezone.utc)
    held = (datetime.now(timezone.utc).date() - ent.date()).days
    return held >= settings.min_hold_days


# ── Paper trading logic ───────────────────────────────────────────────────────

async def _open_position(rec: InvestmentRecommendation) -> None:
    ticker = rec.ticker
    if ticker in _positions:
        logger.info("Position already open for %s, skipping", ticker)
        return

    price = rec.market_data.current_price if rec.market_data else None
    if not price:
        return

    settings = get_settings()

    if _check_drawdown(settings):
        logger.info("Trading paused (drawdown protection) — skipping %s", ticker)
        return

    if settings.trading_hours_only and not _is_market_open():
        logger.debug("Outside market hours — skipping position for %s", ticker)
        return

    if len(_positions) >= _max_positions_allowed(settings):
        logger.info("Max positions reached (%d) — skipping %s", len(_positions), ticker)
        return

    # PDT conviction filter: tighten minimum confidence as day-trade budget depletes.
    # A new open only becomes a day trade if closed the same day; min_hold_days=1
    # prevents signal reversals, but stop-loss can still trigger same-day.
    # Requiring higher confidence when budget is tight reduces that stop-loss risk.
    dt_count = _day_trades_in_window()
    dt_remaining = settings.max_day_trades - dt_count
    if dt_remaining <= 0:
        logger.warning(
            "PDT limit reached (%d/%d day trades this week) — skipping %s",
            dt_count, settings.max_day_trades, ticker,
        )
        return
    required_conf = _PDT_CONFIDENCE_CAUTIOUS if dt_remaining == 1 else _PDT_CONFIDENCE_NORMAL
    if rec.confidence < required_conf:
        logger.info(
            "PDT filter: skipping %s — confidence %.0f%% < %.0f%% required "
            "(%d/%d day trades used, %d slot remaining)",
            ticker, rec.confidence * 100, required_conf * 100,
            dt_count, settings.max_day_trades, dt_remaining,
        )
        return

    # Settled cash guard: don't open positions with unsettled T+2 funds
    unsettled = _unsettled_amount()
    available_cash = _current_equity(settings) - unsettled
    if available_cash < settings.min_position_usd:
        logger.info("Insufficient settled cash $%.2f (unsettled $%.2f) — skipping %s",
                    available_cash, unsettled, ticker)
        return

    direction = TradeDirection.LONG if rec.signal in (Signal.BUY, Signal.STRONG_BUY) else TradeDirection.SHORT

    # Skip SHORT if Alpaca account has shorting disabled
    if direction == TradeDirection.SHORT and _alpaca and not _alpaca_shorting_enabled:
        logger.info("Skipping SHORT for %s — shorting disabled in Alpaca account", ticker)
        return

    # Apply slippage to simulate bid/ask spread on entry fill
    entry_price = _slippage_price(price, direction, True, settings)
    position_size = min(_compute_position_size(settings), available_cash)

    # Cap position size to actual Alpaca buying power (with 3% buffer) to prevent
    # "insufficient buying power" rejections when app equity diverges from Alpaca balance
    if _alpaca and _alpaca_buying_power > 0:
        alpaca_cap = _alpaca_buying_power * 0.97
        if position_size > alpaca_cap:
            logger.info(
                "Capping position for %s: $%.2f → $%.2f (Alpaca buying power $%.2f)",
                ticker, position_size, alpaca_cap, _alpaca_buying_power,
            )
            position_size = alpaca_cap

    quantity = round(position_size / entry_price, 4)

    # Stop loss: use LLM suggestion but enforce a 3% maximum distance from entry.
    # LLMs tend to set very wide stops (10-15%) which allow huge losses before cutting.
    MAX_STOP_PCT = 0.03
    stop_loss = rec.stop_loss
    if direction == TradeDirection.LONG:
        min_sl = round(price * (1 - MAX_STOP_PCT), 2)
        if stop_loss is None or stop_loss >= price or stop_loss < min_sl:
            stop_loss = min_sl
    else:
        max_sl = round(price * (1 + MAX_STOP_PCT), 2)
        if stop_loss is None or stop_loss <= price or stop_loss > max_sl:
            stop_loss = max_sl

    # Validate target_price
    target = rec.target_price_base
    if target is not None:
        if direction == TradeDirection.LONG and target <= price:
            target = round(price * 1.10, 2)
        elif direction == TradeDirection.SHORT and target >= price:
            target = round(price * 0.90, 2)

    # Submit to Alpaca FIRST — only create internal position if order is accepted
    if _alpaca:
        try:
            side = "buy" if direction == TradeDirection.LONG else "sell"
            order = await _alpaca.submit_order(ticker, quantity, side)
            order_id = order.get("id")
            if order_id:
                asyncio.create_task(_verify_fill(ticker, order_id, str(direction)))
        except Exception as exc:
            logger.error("Alpaca order rejected for %s: %s", ticker, exc)
            await ws_manager.broadcast({
                "type": "alpaca_order_failed",
                "ticker": ticker,
                "message": str(exc),
            })
            return  # don't create phantom position

    pos = Position(
        ticker=ticker,
        company_name=rec.company_name,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=stop_loss,
        target_price=target,
        current_price=price,
        signal=rec.signal,
    )
    _positions[ticker] = pos
    await _save_position(pos)
    equity_now = _current_equity(settings)
    compound_growth = (equity_now - settings.initial_balance) / settings.initial_balance * 100
    logger.info(
        "Opened %s for %s @ $%.4f | equity $%.2f (%+.1f%%) | position $%.2f "
        "| conf %.0f%% | PDT %d/%d",
        direction, ticker, entry_price,
        equity_now, compound_growth, position_size,
        rec.confidence * 100, dt_count, settings.max_day_trades,
    )

    await ws_manager.broadcast({
        "type": "position_opened",
        "ticker": ticker,
        "direction": direction,
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "target_price": target,
        "signal": rec.signal,
    })


async def _close_position(ticker: str, exit_price: float, reason: str) -> ClosedTrade | None:
    pos = _positions.pop(ticker, None)
    if not pos:
        return None

    settings = get_settings()

    # Apply slippage to exit fill price
    fill_price = _slippage_price(exit_price, pos.direction, False, settings)

    mult = 1.0 if pos.direction == TradeDirection.LONG else -1.0
    realized_pnl = (fill_price - pos.entry_price) * pos.quantity * mult
    realized_pnl_pct = ((fill_price - pos.entry_price) / pos.entry_price) * 100.0 * mult

    trade = ClosedTrade(
        ticker=ticker,
        company_name=pos.company_name,
        direction=pos.direction,
        entry_price=pos.entry_price,
        exit_price=fill_price,
        entry_time=pos.entry_time,
        quantity=pos.quantity,
        realized_pnl=round(realized_pnl, 2),
        realized_pnl_pct=round(realized_pnl_pct, 2),
        exit_reason=reason,
    )
    _closed_trades.appendleft(trade)
    await _delete_position(ticker)
    await _save_closed_trade(trade)

    if _alpaca:
        try:
            await _alpaca.close_position(ticker)
        except Exception as exc:
            logger.error("Alpaca close failed for %s: %s", ticker, exc)
            await ws_manager.broadcast({
                "type": "alpaca_order_failed",
                "ticker": ticker,
                "message": f"Close failed: {exc}",
            })

    # Day trade detection: opened and closed on the same calendar day
    from datetime import timezone, timedelta
    ent = pos.entry_time if pos.entry_time.tzinfo else pos.entry_time.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).date()
    if ent.date() == today:
        _day_trade_log.append(today)
        logger.info("Day trade logged for %s — %d in rolling 5-day window", ticker, _day_trades_in_window())

    # T+2 settlement: mark proceeds as unsettled
    proceed = abs(fill_price * pos.quantity)
    settle_date = today + timedelta(days=settings.settlement_days)
    _unsettled.append((settle_date, proceed))

    logger.info("Closed %s for %s @ $%.4f (fill) | PnL: $%.2f (%.1f%%) [%s]",
                pos.direction, ticker, fill_price, realized_pnl, realized_pnl_pct, reason)

    await ws_manager.broadcast({
        "type": "position_closed",
        "ticker": ticker,
        "exit_price": fill_price,
        "realized_pnl": trade.realized_pnl,
        "realized_pnl_pct": trade.realized_pnl_pct,
        "exit_reason": reason,
    })
    return trade


MIN_HOLD_SECONDS = 300  # 5 minutes before a signal_reversal can close a position


async def _handle_trade_signal(rec: InvestmentRecommendation) -> None:
    ticker = rec.ticker
    price = rec.market_data.current_price if rec.market_data else None
    if not price:
        return

    is_buy = rec.signal in (Signal.BUY, Signal.STRONG_BUY)
    is_sell = rec.signal in (Signal.SELL, Signal.STRONG_SELL)

    existing = _positions.get(ticker)

    if existing:
        reversal = (
            (existing.direction == TradeDirection.LONG and is_sell) or
            (existing.direction == TradeDirection.SHORT and is_buy)
        )
        if reversal:
            from datetime import timezone
            entry = existing.entry_time
            # Make both datetimes timezone-aware for comparison
            if entry.tzinfo is None:
                from datetime import timezone
                entry = entry.replace(tzinfo=timezone.utc)
            from datetime import datetime as _dt
            now = _dt.now(timezone.utc)
            held_seconds = (now - entry).total_seconds()
            if held_seconds < MIN_HOLD_SECONDS:
                logger.debug(
                    "Skipping signal reversal for %s — held only %.0fs (min %ds)",
                    ticker, held_seconds, MIN_HOLD_SECONDS,
                )
                return
            # PDT guard: don't reverse a position opened today (would be a day trade)
            settings = get_settings()
            if not _can_close_today(existing, settings):
                logger.info(
                    "PDT guard: skipping reversal for %s — position opened today (min_hold_days=%d)",
                    ticker, settings.min_hold_days,
                )
                return
            await _close_position(ticker, price, "signal_reversal")
        else:
            return  # same direction, hold

    # Open new position on clear signal
    if is_buy or is_sell:
        await _open_position(rec)


# ── Price monitor (checks stop-loss / take-profit every 60s) ─────────────────

async def _price_monitor() -> None:
    try:
        while True:
            await asyncio.sleep(30)
            if not _positions:
                continue
            tickers = list(_positions.keys())
            try:
                loop = asyncio.get_event_loop()
                prices: dict[str, float] = {}
                for t in tickers:
                    try:
                        info = await loop.run_in_executor(
                            None, lambda tk=t: yf.Ticker(tk).fast_info
                        )
                        p = getattr(info, "last_price", None)
                        if p:
                            prices[t] = float(p)
                    except Exception:
                        pass

                for ticker, pos in list(_positions.items()):
                    price = prices.get(ticker)
                    if not price:
                        continue

                    pos.current_price = price
                    await _save_position(pos)

                    pnl = pos.unrealized_pnl()
                    pnl_pct = pos.unrealized_pnl_pct()

                    await ws_manager.broadcast({
                        "type": "position_update",
                        "ticker": ticker,
                        "current_price": price,
                        "unrealized_pnl": round(pnl, 2) if pnl is not None else None,
                        "unrealized_pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
                    })

                    # Stop-loss check
                    if pos.stop_loss:
                        if pos.direction == TradeDirection.LONG and price <= pos.stop_loss:
                            await _close_position(ticker, price, "stop_loss")
                            continue
                        if pos.direction == TradeDirection.SHORT and price >= pos.stop_loss:
                            await _close_position(ticker, price, "stop_loss")
                            continue

                    # Take-profit check — PDT guard: skip if position opened today
                    if pos.target_price:
                        triggered = (
                            (pos.direction == TradeDirection.LONG and price >= pos.target_price) or
                            (pos.direction == TradeDirection.SHORT and price <= pos.target_price)
                        )
                        if triggered:
                            tp_settings = get_settings()
                            if _can_close_today(pos, tp_settings):
                                await _close_position(ticker, price, "take_profit")
                            else:
                                logger.debug("PDT guard: holding %s take-profit — opened today", ticker)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Price monitor error: %s", exc)
    except asyncio.CancelledError:
        pass


# ── Scanner alert listener ────────────────────────────────────────────────────

async def _scanner_listener(redis_url: str) -> None:
    stream = "stream:scanner:alerts"
    last_id = "$"
    r: aioredis.Redis | None = None

    async def _connect() -> aioredis.Redis:
        return aioredis.from_url(redis_url, decode_responses=True, socket_keepalive=True)

    try:
        r = await _connect()
        logger.info("Scanner listener started")
        while True:
            try:
                entries = await r.xread({stream: last_id}, block=5000, count=10)
                for _, messages in entries or []:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            payload = json.loads(fields.get("data", "{}"))
                            alert = ScannerAlert(**payload)
                            _scanner_scores[alert.ticker] = alert.combined_score
                            await ws_manager.broadcast({
                                "type": "scanner_alert",
                                "ticker": alert.ticker,
                                "direction": alert.alert_direction,
                                "score": alert.combined_score,
                                "signals": [s.signal_type for s in alert.signals],
                                "price": alert.current_price,
                                "timestamp": alert.timestamp.isoformat(),
                            })
                            if _coordinator:
                                now = time.monotonic()
                                if now < _llm_paused_until:
                                    logger.debug(
                                        "Scanner auto-analysis paused (LLM circuit breaker, %.0fs remaining)",
                                        _llm_paused_until - now,
                                    )
                                else:
                                    last = _last_analysis_time.get(alert.ticker, 0)
                                    already_queued = alert.ticker in _scan_queued
                                    already_active = alert.ticker in _active_tasks
                                    cooldown_ok = now - last >= ANALYSIS_COOLDOWN_SECONDS
                                    if cooldown_ok and not already_queued and not already_active:
                                        _last_analysis_time[alert.ticker] = now
                                        _scan_queued.add(alert.ticker)
                                        await _scan_queue.put(alert.ticker)
                                        logger.debug(
                                            "Queued auto-analysis for %s (queue depth: %d)",
                                            alert.ticker, _scan_queue.qsize(),
                                        )
                                    elif not cooldown_ok:
                                        remaining = int(ANALYSIS_COOLDOWN_SECONDS - (now - last))
                                        logger.debug(
                                            "Skipping %s — cooldown %ds remaining",
                                            alert.ticker, remaining,
                                        )
                        except Exception as exc:
                            logger.warning("Failed to process scanner alert: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Scanner stream error, reconnecting: %s", exc)
                try:
                    await r.aclose()
                except Exception:
                    pass
                await asyncio.sleep(5)
                r = await _connect()
        await r.aclose()
    except asyncio.CancelledError:
        if r:
            await r.aclose()


async def _make_progress_cb(ticker: str):
    async def _cb(step: str, message: str) -> None:
        await ws_manager.broadcast({
            "type": "analysis_progress",
            "ticker": ticker,
            "step": step,
            "message": message,
        })
    return _cb


async def _auto_analyze(ticker: str) -> None:
    global _consecutive_llm_failures, _llm_paused_until
    if not _coordinator:
        return
    progress_cb = await _make_progress_cb(ticker)
    try:
        await ws_manager.broadcast({"type": "analysis_started", "ticker": ticker})

        # Queue 2 (fast): always use cached sentiment or neutral fallback.
        # Sentiment is handled exclusively by Queue 1 (_sentiment_worker).
        cached = _get_cached_sentiment(ticker)
        if cached is not None:
            age_h = round((time.time() - _sentiment_cache[ticker][1]) / 3600, 1)
            logger.info("Fast path for %s — cached sentiment %sh old", ticker, age_h)
        else:
            cached = _neutral_sentiment(ticker)
            logger.info("Fast path for %s — no sentiment cache, using neutral fallback", ticker)

        rec = await _coordinator.analyze(ticker, on_progress=progress_cb, cached_sentiment=cached)

        _consecutive_llm_failures = 0  # reset circuit breaker on success
        summary = _rec_to_dict(rec)
        _recent_analyses.appendleft(summary)
        await _save_analysis_to_redis(summary)
        await ws_manager.broadcast({"type": "analysis_complete", "ticker": ticker, "data": summary})
        await _handle_trade_signal(rec)
    except asyncio.CancelledError:
        await ws_manager.broadcast({"type": "analysis_cancelled", "ticker": ticker})
    except Exception as exc:
        _consecutive_llm_failures += 1
        logger.exception("Auto-analysis failed for %s", ticker)
        if _consecutive_llm_failures >= _LLM_FAILURE_THRESHOLD:
            _llm_paused_until = time.monotonic() + _LLM_PAUSE_SECONDS
            logger.warning(
                "LLM unreachable — pausing scanner auto-analysis for %ds after %d consecutive failures",
                _LLM_PAUSE_SECONDS, _consecutive_llm_failures,
            )
        await ws_manager.broadcast({"type": "error", "ticker": ticker, "message": str(exc)})
    finally:
        _active_tasks.pop(ticker, None)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Financial Intelligence Hub",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    await ws.send_text(json.dumps({"type": "connected", "clients": ws_manager.connected_count}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/watchlist", tags=["Watchlist"])
async def get_watchlist() -> dict[str, Any]:
    if not _redis:
        return {"tickers": []}
    tickers = sorted(await _redis.smembers(WATCHLIST_KEY))
    return {"tickers": tickers}


@app.post("/watchlist/{ticker}", tags=["Watchlist"])
async def add_to_watchlist(ticker: str = Path(...)) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 10:
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    if _redis:
        await _redis.sadd(WATCHLIST_KEY, ticker)
    return {"ticker": ticker, "action": "added"}


@app.delete("/watchlist/{ticker}", tags=["Watchlist"])
async def remove_from_watchlist(ticker: str = Path(...)) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    if _redis:
        await _redis.srem(WATCHLIST_KEY, ticker)
    return {"ticker": ticker, "action": "removed"}


# ── Analysis ──────────────────────────────────────────────────────────────────

@app.post("/analyze/{ticker}", tags=["Analysis"])
async def analyze_ticker(ticker: str = Path(...)) -> dict[str, Any]:
    if not _coordinator:
        raise HTTPException(status_code=503, detail="Coordinator not initialized")
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 10:
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")

    if ticker in _active_tasks:
        raise HTTPException(status_code=409, detail=f"Analysis for {ticker} already in progress")

    start = time.monotonic()
    await ws_manager.broadcast({"type": "analysis_started", "ticker": ticker})

    progress_cb = await _make_progress_cb(ticker)

    async def _run() -> None:
        nonlocal summary_box
        try:
            rec = await _coordinator.analyze(ticker, on_progress=progress_cb)
            summary = _rec_to_dict(rec)
            summary["meta"]["analysis_duration_seconds"] = round(time.monotonic() - start, 2)
            _recent_analyses.appendleft(summary)
            await _save_analysis_to_redis(summary)
            _last_analysis_time[ticker] = time.monotonic()
            await ws_manager.broadcast({"type": "analysis_complete", "ticker": ticker, "data": summary})
            await _handle_trade_signal(rec)
            summary_box.append(summary)
        except asyncio.CancelledError:
            await ws_manager.broadcast({"type": "analysis_cancelled", "ticker": ticker})
        except Exception as exc:
            await ws_manager.broadcast({"type": "error", "ticker": ticker, "message": str(exc)})
            summary_box.append({"error": str(exc)})
        finally:
            _active_tasks.pop(ticker, None)

    summary_box: list[dict[str, Any]] = []
    task = asyncio.create_task(_run())
    _active_tasks[ticker] = task
    try:
        await task
    except Exception:
        pass

    if not summary_box:
        raise HTTPException(status_code=500, detail="Analysis failed")
    result = summary_box[0]
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/analyses", tags=["Analysis"])
async def get_recent_analyses() -> dict[str, Any]:
    return {"analyses": list(_recent_analyses)}


@app.get("/analyses/active", tags=["Analysis"])
async def get_active_analyses() -> dict[str, Any]:
    return {"active": list(_active_tasks.keys())}


@app.delete("/analyze", tags=["Analysis"])
async def cancel_all_analyses() -> dict[str, Any]:
    tickers = list(_active_tasks.keys())
    for task in list(_active_tasks.values()):
        task.cancel()
    return {"cancelled": tickers, "count": len(tickers)}


@app.delete("/analyze/{ticker}", tags=["Analysis"])
async def cancel_analysis(ticker: str = Path(...)) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    task = _active_tasks.get(ticker)
    if not task:
        raise HTTPException(status_code=404, detail=f"No active analysis for {ticker}")
    task.cancel()
    return {"ticker": ticker, "action": "cancelled"}


@app.delete("/analyses", tags=["Analysis"])
async def clear_analyses() -> dict[str, Any]:
    global _consecutive_llm_failures, _llm_paused_until
    _recent_analyses.clear()
    _last_analysis_time.clear()
    _consecutive_llm_failures = 0
    _llm_paused_until = 0.0
    # Note: _auto_analysis_count is NOT reset here — active tasks are still running
    # until cancelled via DELETE /analyze.
    if _redis:
        await _redis.delete(ANALYSES_KEY)
    return {"action": "cleared"}


@app.get("/analyze/{ticker}/quick", tags=["Analysis"])
async def quick_snapshot(ticker: str = Path(...)) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    try:
        from market_data_agent.agent import MarketDataAgent
        settings = get_settings()
        agent = MarketDataAgent(settings)
        stock_data = await agent.analyze(ticker)
        await agent.close()
        t = stock_data.technicals
        return {
            "ticker": stock_data.ticker,
            "company": stock_data.company_name,
            "price": stock_data.current_price,
            "change_pct": stock_data.price_change_pct,
            "technicals": {"rsi_14": t.rsi_14, "macd": t.macd, "sma_50": t.sma_50, "sma_200": t.sma_200},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Candles ───────────────────────────────────────────────────────────────────

@app.get("/candles/{ticker}", tags=["Market Data"])
async def get_candles(
    ticker: str = Path(...),
    period: str = "6mo",
    interval: str = "1d",
) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.Ticker(ticker).history(period=period, interval=interval),
        )
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")
        candles = [
            {
                "time": str(row.name.date() if hasattr(row.name, "date") else row.name),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            }
            for _, row in df.iterrows()
        ]
        return {"ticker": ticker, "period": period, "interval": interval, "candles": candles}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.get("/portfolio", tags=["Portfolio"])
async def get_portfolio() -> dict[str, Any]:
    open_positions = []
    for ticker, pos in _positions.items():
        pnl = pos.unrealized_pnl()
        pnl_pct = pos.unrealized_pnl_pct()
        open_positions.append({
            "ticker": ticker,
            "company_name": pos.company_name,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "current_price": pos.current_price,
            "quantity": pos.quantity,
            "stop_loss": pos.stop_loss,
            "target_price": pos.target_price,
            "unrealized_pnl": round(pnl, 2) if pnl is not None else None,
            "unrealized_pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "entry_time": pos.entry_time.isoformat(),
            "signal": pos.signal,
        })

    closed = [
        {
            "ticker": t.ticker,
            "company_name": t.company_name,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "realized_pnl": t.realized_pnl,
            "realized_pnl_pct": t.realized_pnl_pct,
            "exit_reason": t.exit_reason,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat(),
        }
        for t in _closed_trades
    ]

    total_open_pnl = sum(
        p.unrealized_pnl() or 0 for p in _positions.values()
    )
    total_realized_pnl = sum(t.realized_pnl for t in _closed_trades)

    settings = get_settings()
    equity = _current_equity(settings)
    initial = settings.initial_balance
    drawdown_pct = round((_peak_equity - equity) / _peak_equity * 100, 2) if _peak_equity > 0 else 0.0
    growth_pct = round((equity - initial) / initial * 100, 2) if initial > 0 else 0.0
    max_positions = _max_positions_allowed(settings)
    dt_used = _day_trades_in_window()
    dt_remaining = max(0, settings.max_day_trades - dt_used)
    pdt_min_conf = _PDT_CONFIDENCE_CAUTIOUS if dt_remaining <= 1 else _PDT_CONFIDENCE_NORMAL
    next_position_size = round(min(_compute_position_size(settings), equity), 2)

    return {
        "open_positions": open_positions,
        "closed_trades": closed,
        "summary": {
            "open_count": len(open_positions),
            "closed_count": len(closed),
            "total_open_pnl": round(total_open_pnl, 2),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_pnl": round(total_open_pnl + total_realized_pnl, 2),
            "equity": round(equity, 2),
            "initial_balance": round(initial, 2),
            "peak_equity": round(_peak_equity, 2),
            "drawdown_pct": drawdown_pct,
            "growth_pct": growth_pct,
            "trading_paused": _trading_paused,
            "market_open": _is_market_open(),
            "max_positions_allowed": max_positions,
            "day_trades_in_window": dt_used,
            "day_trades_remaining": dt_remaining,
            "pdt_min_confidence": round(pdt_min_conf, 2),
            "unsettled_cash": round(_unsettled_amount(), 2),
            "slippage_pct": settings.slippage_pct,
            "next_position_size": next_position_size,
        },
    }


@app.delete("/portfolio", tags=["Portfolio"])
async def reset_portfolio() -> dict[str, Any]:
    global _peak_equity, _trading_paused
    closed = list(_positions.keys())
    _positions.clear()
    _closed_trades.clear()
    _day_trade_log.clear()
    _unsettled.clear()
    _peak_equity = 0.0
    _trading_paused = False
    if _redis:
        await _redis.delete(PORTFOLIO_KEY)
        await _redis.delete(CLOSED_TRADES_KEY)

    # Close ALL positions in Alpaca too (including those from previous runs)
    if _alpaca:
        try:
            await _alpaca.close_all_positions()
            logger.info("Alpaca reset: all positions closed")
        except Exception as exc:
            logger.error("Alpaca reset: bulk close failed: %s", exc)

    await ws_manager.broadcast({"type": "portfolio_reset"})
    return {"action": "reset", "closed_positions": closed, "count": len(closed)}


@app.delete("/portfolio/{ticker}", tags=["Portfolio"])
async def close_position_manual(ticker: str = Path(...)) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    pos = _positions.get(ticker)
    if not pos:
        raise HTTPException(status_code=404, detail=f"No open position for {ticker}")
    price = pos.current_price or pos.entry_price
    trade = await _close_position(ticker, price, "manual")
    if not trade:
        raise HTTPException(status_code=500, detail="Failed to close position")
    return {"ticker": ticker, "realized_pnl": trade.realized_pnl, "exit_reason": "manual"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/alpaca/account", tags=["Alpaca"])
async def alpaca_account() -> dict[str, Any]:
    if not _alpaca:
        raise HTTPException(status_code=503, detail="Alpaca not configured (set ALPACA_MODE, ALPACA_API_KEY, ALPACA_API_SECRET in .env)")
    try:
        account = await _alpaca.get_account()
        positions = await _alpaca.get_positions()
        return {
            "mode": _alpaca._mode,
            "account_id": account.get("id"),
            "status": account.get("status"),
            "buying_power": float(account.get("buying_power", 0)),
            "cash": float(account.get("cash", 0)),
            "portfolio_value": float(account.get("portfolio_value", 0)),
            "equity": float(account.get("equity", 0)),
            "last_equity": float(account.get("last_equity", 0)),
            "pnl_today": float(account.get("equity", 0)) - float(account.get("last_equity", 0)),
            "open_positions": len(positions),
            "positions": [
                {
                    "ticker": p["symbol"],
                    "qty": float(p["qty"]),
                    "side": p["side"],
                    "entry_price": float(p["avg_entry_price"]),
                    "current_price": float(p["current_price"]),
                    "unrealized_pnl": float(p["unrealized_pl"]),
                    "unrealized_pnl_pct": float(p["unrealized_plpc"]) * 100,
                    "market_value": float(p["market_value"]),
                }
                for p in positions
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Alpaca API error: {exc}")


@app.get("/alpaca/orders", tags=["Alpaca"])
async def alpaca_orders(status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    if not _alpaca:
        raise HTTPException(status_code=503, detail="Alpaca not configured")
    try:
        orders = await _alpaca.get_orders(status=status, limit=limit)
        return [
            {
                "id": o.get("id"),
                "ticker": o.get("symbol"),
                "side": o.get("side"),
                "qty": o.get("qty"),
                "filled_qty": o.get("filled_qty"),
                "type": o.get("type"),
                "status": o.get("status"),
                "filled_avg_price": o.get("filled_avg_price"),
                "submitted_at": o.get("submitted_at"),
                "filled_at": o.get("filled_at"),
            }
            for o in orders
        ]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Alpaca API error: {exc}")


@app.get("/health", tags=["System"])
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": "2.0.0",
        "ws_clients": ws_manager.connected_count,
        "recent_analyses": len(_recent_analyses),
        "open_positions": len(_positions),
        "alpaca_enabled": _alpaca is not None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rec_to_dict(rec: InvestmentRecommendation) -> dict[str, Any]:
    chart = rec.chart_analysis
    return {
        "ticker": rec.ticker,
        "company_name": rec.company_name,
        "signal": rec.signal,
        "confidence": rec.confidence,
        "risk_level": rec.risk_level,
        "current_price": rec.market_data.current_price if rec.market_data else None,
        "targets": {
            "bull": rec.target_price_bull,
            "base": rec.target_price_base,
            "bear": rec.target_price_bear,
            "stop_loss": rec.stop_loss,
        },
        "time_horizon_days": rec.time_horizon_days,
        "scores": {
            "technical": rec.technical_score,
            "fundamental": rec.fundamental_score,
            "sentiment": rec.sentiment_score,
            "risk_adjusted": rec.risk_adjusted_score,
        },
        "analysis": {
            "executive_summary": rec.executive_summary,
            "bull_case": rec.bull_case,
            "bear_case": rec.bear_case,
            "key_risks": rec.key_risks,
            "key_catalysts": rec.key_catalysts,
        },
        "chart": {
            "trend": chart.trend if chart else None,
            "trend_strength": chart.trend_strength if chart else None,
            "chart_signal": chart.chart_signal if chart else None,
            "chart_confidence": chart.confidence if chart else None,
            "patterns": [p.name for p in chart.patterns] if chart else [],
            "support_levels": chart.support_levels if chart else [],
            "resistance_levels": chart.resistance_levels if chart else [],
            "chart_summary": chart.chart_summary if chart else None,
        },
        "sentiment": {
            "label": rec.sentiment_data.label if rec.sentiment_data else None,
            "overall_score": rec.sentiment_data.overall_score if rec.sentiment_data else None,
        },
        "meta": {
            "agents_used": rec.agents_used,
            "timestamp": rec.timestamp.isoformat(),
            "analysis_duration_seconds": rec.analysis_duration_seconds,
        },
    }
