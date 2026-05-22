# Multi-Agent Financial Intelligence Hub

> AI-powered investment analysis platform with specialized agents working in concert.
> Supports **Ollama (default), Anthropic, OpenAI, Gemini, Groq, Mistral, Together AI**, and any other [LiteLLM](https://docs.litellm.ai/docs/providers)-compatible provider.

## Features

- **5 specialized AI agents** — market data, sentiment, chart vision, risk analysis, and market scanner
- **Real-time web dashboard** — React + TypeScript frontend with live WebSocket updates
- **Interactive charts** — candlestick + volume + RSI + MACD + Bollinger Bands, synced panes
- **Paper trading** — auto buy/sell on signals, stop-loss/take-profit monitoring, P&L tracking
- **Watchlist** — 49 pre-seeded tickers (S&P 500, ETFs, crypto-adjacent), add/remove anytime
- **Activity feed** — real-time stream of scanner alerts, analysis events, and trade executions
- **State persistence** — analyses, portfolio, and watchlist survive service restarts (Redis-backed)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                React Frontend  (port 3040)                          │
│         Watchlist · Charts · Portfolio · Activity Feed              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP + WebSocket (nginx proxy → /api, /ws)
┌──────────────────────────▼──────────────────────────────────────────┐
│                  FastAPI Orchestrator  (port 8000)                  │
│   REST API · WebSocket broadcast · Paper trading · Task manager     │
└──┬───────────────────────┬──────────────────┬───────────────────────┘
   │ asyncio.gather        │                  │
   ▼                       ▼                  ▼
┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐
│ Market Data  │  │ Sentiment Agent │  │ Chart Vision Agent│
│ Agent        │  │                 │  │                   │
│ • price/OHLCV│  │ • Reddit/news   │  │ • mplfinance chart│
│ • technicals │  │ • Fear & Greed  │  │ • LLM vision      │
│ • fundamentals│ │ • analyst rtgs  │  │ • pattern detect  │
│ • options    │  │                 │  │ • trend analysis  │
└──────┬───────┘  └────────┬────────┘  └────────┬──────────┘
       │                   │                    │
       └──────────┬────────┘                   │
                  ▼                             │
        ┌─────────────────┐                    │
        │   Risk Agent    │◄───────────────────┘
        │                 │
        │ • quant metrics │
        │ • position size │
        │ • price targets │
        │ • final signal  │
        └────────┬────────┘
                 │
                 ▼
     ┌────────────────────────┐
     │  InvestmentRecommend.  │
     │  signal: BUY / SELL …  │
     │  confidence: 0.72      │
     │  targets: bull/base/bear│
     │  stop_loss: $188       │
     └────────────────────────┘

Scanner Agent (background)
  • Monitors all watchlist tickers every 5 min
  • Publishes alerts to Redis Streams
  • Orchestrator auto-analyses on strong signals
```

---

## Agents

### 1. Market Data Agent
Extracts real-time financial data using **LLM + tool use**:
- Live price, OHLCV, 52-week range
- Technical indicators: RSI, MACD, Bollinger Bands, SMA/EMA, ADX, ATR
- Fundamental metrics: P/E, PEG, EPS growth, margins, debt ratios, ROE
- Options flow: implied volatility, put/call ratio
- Market context: VIX level, S&P 500 relative strength

### 2. Sentiment Agent
Analyzes social media and news using **LLM + tool use**:
- Reddit finance subreddits (r/wallstreetbets, r/stocks, r/investing, etc.)
- News articles via NewsAPI
- Fear & Greed Index
- Wall Street analyst ratings and consensus targets
- Outputs sentiment score (-1 to +1), themes, and catalysts

### 3. Chart Vision Agent
Analyzes price charts visually using **LLM vision**:
- Renders candlestick chart with mplfinance
- Identifies chart patterns (head & shoulders, triangles, flags, etc.)
- Trend analysis and momentum signals
- Support/resistance levels from visual inspection

### 4. Risk Agent
Synthesizes all outputs into a recommendation using **LLM + tool use**:
- Quantitative risk: VaR (95%/99%), Expected Shortfall, Sharpe, Sortino, Max Drawdown
- Beta, market correlation, Calmar ratio
- ATR-based position sizing and price targets (bull/base/bear)
- Final signal: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL

### 5. Scanner Agent
Continuously monitors the watchlist in the background:
- Evaluates all tickers every 5 minutes
- Scores each ticker across technical indicators
- Publishes strong signals to Redis Streams for the orchestrator to auto-analyze
- 30-minute cooldown per ticker to prevent spam

---

## Quick Start (Docker)

```bash
git clone https://github.com/your-org/multi-agent-financial-intelligence-hub.git
cd multi-agent-financial-intelligence-hub

# Configure LLM provider (Ollama by default — no API key needed)
cp .env.example .env

# Start Ollama and pull a model
ollama serve
ollama pull llama3.2   # or qwen2.5, llama3.1, mistral-nemo

# Launch full stack
docker compose up -d

# Open the dashboard
open http://localhost:3040
```

The watchlist is pre-seeded with 49 tickers (AAPL, TSLA, NVDA, SPY, QQQ, …). Click any ticker to see its chart. Click ⚡ to run a full multi-agent analysis.

---

## Manual Setup (without Docker)

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.12+ | [python.org](https://www.python.org/downloads/) or `pyenv install 3.12` |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js 20+ | [nodejs.org](https://nodejs.org/) |
| Docker + Compose | [docs.docker.com](https://docs.docker.com/get-docker/) (Redis + Postgres) |
| Ollama *(default)* | [ollama.com](https://ollama.com/download) |

### Step 1 — Install dependencies

```bash
# Python packages (uv workspace)
make dev
# equivalent: uv sync --all-packages

# Frontend
cd packages/frontend && npm install
```

### Step 2 — Configure environment

```bash
cp .env.example .env
```

**By default, Ollama is used — no API key required.**

#### Ollama (default)

```bash
ollama serve
ollama pull llama3.2       # 3B — fast, good for dev
# ollama pull llama3.1     # 8B — better quality
# ollama pull qwen2.5      # strong tool-use
```

#### Anthropic

```env
ANTHROPIC_API_KEY=sk-ant-...
MARKET_DATA_AGENT_MODEL=anthropic/claude-sonnet-4-6
SENTIMENT_AGENT_MODEL=anthropic/claude-sonnet-4-6
RISK_AGENT_MODEL=anthropic/claude-sonnet-4-6
```

#### OpenAI

```env
OPENAI_API_KEY=sk-...
MARKET_DATA_AGENT_MODEL=openai/gpt-4o
SENTIMENT_AGENT_MODEL=openai/gpt-4o
RISK_AGENT_MODEL=openai/gpt-4o
```

#### Groq (fast inference)

```env
GROQ_API_KEY=gsk_...
MARKET_DATA_AGENT_MODEL=groq/llama-3.3-70b-versatile
SENTIMENT_AGENT_MODEL=groq/llama-3.3-70b-versatile
RISK_AGENT_MODEL=groq/llama-3.3-70b-versatile
```

> **Mix providers per agent:**
> ```env
> MARKET_DATA_AGENT_MODEL=groq/llama-3.3-70b-versatile
> SENTIMENT_AGENT_MODEL=groq/llama-3.3-70b-versatile
> RISK_AGENT_MODEL=anthropic/claude-sonnet-4-6
> ```

### Step 3 — Start infrastructure

```bash
make docker-up   # Redis + Postgres
```

### Step 4 — Start services

```bash
# Terminal 1 — Orchestrator API
cd packages/orchestrator && uv run python -m orchestrator.main

# Terminal 2 — Scanner Agent
cd packages/scanner-agent && uv run python -m scanner_agent.main

# Terminal 3 — Frontend dev server
cd packages/frontend && npm run dev
# → http://localhost:5173
```

---

## LLM Provider Reference

| Provider | Prefix | Example model | Tool use |
|----------|--------|---------------|----------|
| **Ollama** (default) | `ollama/` | `ollama/llama3.2` | ✅ llama3.x, qwen2.5, mistral |
| Anthropic | `anthropic/` | `anthropic/claude-sonnet-4-6` | ✅ all Claude models |
| OpenAI | `openai/` | `openai/gpt-4o` | ✅ GPT-4o, GPT-4o-mini |
| Google Gemini | `gemini/` | `gemini/gemini-1.5-flash` | ✅ 1.5 Flash / Pro |
| Groq | `groq/` | `groq/llama-3.3-70b-versatile` | ✅ Llama 3.x, Mixtral |
| Mistral | `mistral/` | `mistral/mistral-large-latest` | ✅ Large, Small |
| Together AI | `together_ai/` | `together_ai/meta-llama/Llama-3-70b-chat-hf` | ✅ varies |

Uses [LiteLLM](https://docs.litellm.ai/docs/providers) — any of the 100+ supported providers work as long as their model supports tool/function calling.

---

## Project Structure

```
multi-agent-financial-intelligence-hub/
├── packages/
│   ├── shared/                 # Pydantic models, config, LLM client
│   ├── market-data-agent/      # Agent 1: Real-time financial data
│   ├── sentiment-agent/        # Agent 2: Social media & news sentiment
│   ├── chart-vision-agent/     # Agent 3: Visual chart pattern recognition
│   ├── risk-agent/             # Agent 4: Risk analysis & recommendation
│   ├── scanner-agent/          # Agent 5: Background market scanner
│   ├── orchestrator/           # FastAPI server, paper trading, task manager
│   └── frontend/               # React + TypeScript + Tailwind dashboard
│       ├── src/
│       │   ├── components/
│       │   │   ├── Watchlist.tsx       # Ticker list with add/remove/analyze
│       │   │   ├── AnalysisCard.tsx    # Full analysis result + chart
│       │   │   ├── TickerPanel.tsx     # Chart-only view (pre-analysis)
│       │   │   ├── CandleChart.tsx     # Candlestick + RSI + MACD panes
│       │   │   ├── Portfolio.tsx       # Open positions + closed trades
│       │   │   └── ActivityFeed.tsx    # Real-time event stream
│       │   ├── hooks/
│       │   │   └── useWebSocket.ts     # Auto-reconnect WebSocket
│       │   └── lib/
│       │       ├── api.ts              # REST API client
│       │       └── indicators.ts       # RSI, MACD, Bollinger Bands, SMA
│       └── nginx.conf                  # Reverse proxy: /api → orchestrator
├── .env.example
├── docker-compose.yml          # Full stack (ports: frontend 3040, api 8005)
└── Makefile
```

---

## API Reference

All endpoints are available at `http://localhost:8005` (direct) or `http://localhost:3040/api` (via nginx proxy).

### Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze/{ticker}` | Start multi-agent analysis (async, results via WebSocket) |
| `DELETE` | `/analyze/{ticker}` | Cancel in-progress analysis |
| `GET` | `/analyses` | List recent completed analyses (Redis-backed) |
| `GET` | `/analyses/active` | List tickers currently being analyzed |
| `GET` | `/candles/{ticker}` | OHLCV candle data (`?period=6mo`) |

### Watchlist

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/watchlist` | Get all tickers |
| `POST` | `/watchlist/{ticker}` | Add ticker |
| `DELETE` | `/watchlist/{ticker}` | Remove ticker |

### Portfolio (Paper Trading)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/portfolio` | Open positions, closed trades, and P&L summary |
| `DELETE` | `/portfolio/{ticker}` | Manually close a position |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `WebSocket` | `/ws` | Real-time event stream |

### WebSocket Events

```jsonc
{ "type": "analysis_started",  "ticker": "AAPL" }
{ "type": "analysis_complete", "ticker": "AAPL", "data": { /* Analysis */ } }
{ "type": "analysis_cancelled","ticker": "AAPL" }
{ "type": "error",             "ticker": "AAPL", "message": "..." }
{ "type": "scanner_alert",     "ticker": "TSLA", "direction": "LONG", "score": 0.82, "signals": ["RSI oversold", "MACD cross"] }
{ "type": "position_opened",   "ticker": "NVDA", "direction": "LONG", "entry_price": 420.0, "quantity": 23 }
{ "type": "position_closed",   "ticker": "NVDA", "realized_pnl": 184.50, "exit_reason": "take_profit" }
{ "type": "position_update",   "ticker": "NVDA", "current_price": 428.30, "unrealized_pnl": 191.90 }
```

---

## Paper Trading

When a completed analysis produces a strong signal (STRONG_BUY or STRONG_SELL), the orchestrator automatically:

1. **Opens a position** — allocates $10,000 per trade, calculates quantity from current price
2. **Sets stop-loss and target** — from the risk agent's price targets
3. **Monitors every 60 seconds** — checks live prices via yfinance
4. **Closes the position** when stop-loss, take-profit, or 30-day max hold is hit
5. **Broadcasts P&L** — all events stream via WebSocket to the dashboard

The Portfolio tab shows open positions with live unrealized P&L and the full history of closed trades.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| AI / LLM | LiteLLM (Ollama default; Anthropic, OpenAI, Gemini, Groq, …) |
| Language | Python 3.12, TypeScript |
| API Framework | FastAPI + uvicorn |
| Data Models | Pydantic v2 |
| Frontend | React 18, Vite, Tailwind CSS |
| Charts | lightweight-charts v4 (TradingView) |
| Market Data | yfinance |
| Social Data | PRAW (Reddit), NewsAPI |
| Chart Rendering | mplfinance + Pillow |
| Message Bus | Redis Streams |
| Persistence | Redis (watchlist, analyses, portfolio) |
| Reverse Proxy | nginx (static files + API proxy) |
| Package Manager | uv workspaces (Python), npm (frontend) |
| Containers | Docker + Docker Compose |

---

## Ports

| Service | Docker port | Direct |
|---------|------------|--------|
| Frontend (nginx) | `3040` | `http://localhost:3040` |
| Orchestrator API | `8005` | `http://localhost:8005` |
| Redis | `6380` | `localhost:6380` |
| PostgreSQL | `5434` | `localhost:5434` |

---

## Disclaimer

This software is for **educational and research purposes only**.
It does not constitute financial advice. Always consult a licensed financial
advisor before making investment decisions. The paper trading simulation uses
delayed market data and does not reflect real-world execution conditions.
