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
    Signal,
    TradeDirection,
)

from orchestrator.coordinator import AgentCoordinator
from orchestrator.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

_coordinator: AgentCoordinator | None = None
_message_bus: MessageBus | None = None
_redis: aioredis.Redis | None = None

_recent_analyses: deque[dict[str, Any]] = deque(maxlen=50)

# Analysis dedup: ticker → epoch seconds of last triggered analysis
_last_analysis_time: dict[str, float] = {}
ANALYSIS_COOLDOWN_SECONDS = 1800  # 30 minutes

# Active analysis tasks: ticker → asyncio.Task (for cancellation)
_active_tasks: dict[str, asyncio.Task[None]] = {}

ANALYSES_KEY = "fintelligence:analyses"

# Paper portfolio (in-memory; Redis-backed for persistence)
_positions: dict[str, Position] = {}     # ticker → open position
_closed_trades: deque[ClosedTrade] = deque(maxlen=200)
POSITION_SIZE_USD = 10_000.0             # dollars per trade

WATCHLIST_KEY = "fintelligence:watchlist"
PORTFOLIO_KEY = "fintelligence:portfolio"
CLOSED_TRADES_KEY = "fintelligence:closed_trades"


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _coordinator, _message_bus, _redis

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        logger.info("Redis connected")
        await _load_portfolio_from_redis()
        await _load_analyses_from_redis()
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
    logger.info("Financial Intelligence Hub API started")

    scanner_task = asyncio.create_task(_scanner_listener(settings.redis_url))
    price_task = asyncio.create_task(_price_monitor())

    yield

    scanner_task.cancel()
    price_task.cancel()
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


# ── Paper trading logic ───────────────────────────────────────────────────────

async def _open_position(rec: InvestmentRecommendation) -> None:
    ticker = rec.ticker
    if ticker in _positions:
        logger.info("Position already open for %s, skipping", ticker)
        return

    price = rec.market_data.current_price if rec.market_data else None
    if not price:
        return

    direction = TradeDirection.LONG if rec.signal in (Signal.BUY, Signal.STRONG_BUY) else TradeDirection.SHORT
    quantity = round(POSITION_SIZE_USD / price, 4)

    pos = Position(
        ticker=ticker,
        company_name=rec.company_name,
        direction=direction,
        entry_price=price,
        quantity=quantity,
        stop_loss=rec.stop_loss,
        target_price=rec.target_price_base,
        current_price=price,
        signal=rec.signal,
    )
    _positions[ticker] = pos
    await _save_position(pos)
    logger.info("Opened %s position for %s @ $%.2f", direction, ticker, price)

    await ws_manager.broadcast({
        "type": "position_opened",
        "ticker": ticker,
        "direction": direction,
        "entry_price": price,
        "quantity": quantity,
        "stop_loss": rec.stop_loss,
        "target_price": rec.target_price_base,
        "signal": rec.signal,
    })


async def _close_position(ticker: str, exit_price: float, reason: str) -> ClosedTrade | None:
    pos = _positions.pop(ticker, None)
    if not pos:
        return None

    mult = 1.0 if pos.direction == TradeDirection.LONG else -1.0
    realized_pnl = (exit_price - pos.entry_price) * pos.quantity * mult
    realized_pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100.0 * mult

    trade = ClosedTrade(
        ticker=ticker,
        company_name=pos.company_name,
        direction=pos.direction,
        entry_price=pos.entry_price,
        exit_price=exit_price,
        entry_time=pos.entry_time,
        quantity=pos.quantity,
        realized_pnl=round(realized_pnl, 2),
        realized_pnl_pct=round(realized_pnl_pct, 2),
        exit_reason=reason,
    )
    _closed_trades.appendleft(trade)
    await _delete_position(ticker)
    await _save_closed_trade(trade)

    logger.info("Closed %s for %s @ $%.2f | PnL: $%.2f (%.1f%%) [%s]",
                pos.direction, ticker, exit_price, realized_pnl, realized_pnl_pct, reason)

    await ws_manager.broadcast({
        "type": "position_closed",
        "ticker": ticker,
        "exit_price": exit_price,
        "realized_pnl": trade.realized_pnl,
        "realized_pnl_pct": trade.realized_pnl_pct,
        "exit_reason": reason,
    })
    return trade


async def _handle_trade_signal(rec: InvestmentRecommendation) -> None:
    ticker = rec.ticker
    price = rec.market_data.current_price if rec.market_data else None
    if not price:
        return

    is_buy = rec.signal in (Signal.BUY, Signal.STRONG_BUY)
    is_sell = rec.signal in (Signal.SELL, Signal.STRONG_SELL)

    existing = _positions.get(ticker)

    if existing:
        # Close on signal reversal
        if existing.direction == TradeDirection.LONG and is_sell:
            await _close_position(ticker, price, "signal_reversal")
        elif existing.direction == TradeDirection.SHORT and is_buy:
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
            await asyncio.sleep(60)
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

                    # Take-profit check
                    if pos.target_price:
                        if pos.direction == TradeDirection.LONG and price >= pos.target_price:
                            await _close_position(ticker, price, "take_profit")
                        elif pos.direction == TradeDirection.SHORT and price <= pos.target_price:
                            await _close_position(ticker, price, "take_profit")

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
                                last = _last_analysis_time.get(alert.ticker, 0)
                                if now - last >= ANALYSIS_COOLDOWN_SECONDS and alert.ticker not in _active_tasks:
                                    _last_analysis_time[alert.ticker] = now
                                    task = asyncio.create_task(_auto_analyze(alert.ticker))
                                    _active_tasks[alert.ticker] = task
                                else:
                                    remaining = int(ANALYSIS_COOLDOWN_SECONDS - (now - last))
                                    logger.debug(
                                        "Skipping auto-analysis for %s (cooldown %ds remaining)",
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
    if not _coordinator:
        return
    progress_cb = await _make_progress_cb(ticker)
    try:
        await ws_manager.broadcast({"type": "analysis_started", "ticker": ticker})
        rec = await _coordinator.analyze(ticker, on_progress=progress_cb)
        summary = _rec_to_dict(rec)
        _recent_analyses.appendleft(summary)
        await _save_analysis_to_redis(summary)
        await ws_manager.broadcast({"type": "analysis_complete", "ticker": ticker, "data": summary})
        await _handle_trade_signal(rec)
    except asyncio.CancelledError:
        await ws_manager.broadcast({"type": "analysis_cancelled", "ticker": ticker})
    except Exception as exc:
        logger.exception("Auto-analysis failed for %s", ticker)
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
    _recent_analyses.clear()
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

    return {
        "open_positions": open_positions,
        "closed_trades": closed,
        "summary": {
            "open_count": len(open_positions),
            "closed_count": len(closed),
            "total_open_pnl": round(total_open_pnl, 2),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_pnl": round(total_open_pnl + total_realized_pnl, 2),
        },
    }


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

@app.get("/health", tags=["System"])
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": "2.0.0",
        "ws_clients": ws_manager.connected_count,
        "recent_analyses": len(_recent_analyses),
        "open_positions": len(_positions),
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
