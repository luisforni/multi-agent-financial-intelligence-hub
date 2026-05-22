from __future__ import annotations

import json
import logging
from typing import Any

from shared.models import StockData

logger = logging.getLogger(__name__)

# Tool definitions in OpenAI / LiteLLM format (compatible with all providers)
MARKET_DATA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price_and_technicals",
            "description": (
                "Retrieves real-time price data and technical indicators for a given ticker symbol. "
                "Returns current price, OHLCV data, RSI, MACD, Bollinger Bands, moving averages, "
                "ATR, ADX, and volume analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL, MSFT, TSLA)",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_fundamentals",
            "description": (
                "Retrieves fundamental financial data for a company: P/E ratio, EPS, revenue growth, "
                "profit margins, debt ratios, ROE, market cap, beta, and sector/industry classification."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_options_flow_summary",
            "description": (
                "Retrieves options market data: implied volatility, put/call ratio, max pain price, "
                "and unusual options activity that may signal institutional positioning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol",
                    },
                    "expiry_filter": {
                        "type": "string",
                        "description": "Filter by expiry: 'weekly', 'monthly', 'all'",
                        "enum": ["weekly", "monthly", "all"],
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_context",
            "description": (
                "Retrieves broader market context: S&P 500 trend, VIX level, sector performance, "
                "and relative strength of the stock vs its sector and the broader market."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol to compare against market",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_market_analysis",
            "description": (
                "Submit the final market data analysis. Call this once you have gathered sufficient "
                "data to provide a comprehensive technical and fundamental assessment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "technical_summary": {
                        "type": "string",
                        "description": "Comprehensive technical analysis summary (2-4 paragraphs)",
                    },
                    "fundamental_summary": {
                        "type": "string",
                        "description": "Comprehensive fundamental analysis summary (2-4 paragraphs)",
                    },
                    "technical_score": {
                        "type": "number",
                        "description": "Technical outlook score from 0 (very bearish) to 100 (very bullish)",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "fundamental_score": {
                        "type": "number",
                        "description": "Fundamental quality score from 0 (poor) to 100 (excellent)",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": [
                    "technical_summary",
                    "fundamental_summary",
                    "technical_score",
                    "fundamental_score",
                ],
            },
        },
    },
]


def format_stock_data_for_tool(stock: StockData) -> str:
    t = stock.technicals
    f = stock.fundamentals
    return json.dumps(
        {
            "ticker": stock.ticker,
            "company": stock.company_name,
            "price": stock.current_price,
            "change_pct": stock.price_change_pct,
            "volume": stock.volume,
            "avg_volume": stock.average_volume,
            "week_52_high": stock.week_52_high,
            "week_52_low": stock.week_52_low,
            "technicals": {
                "rsi_14": t.rsi_14,
                "macd": t.macd,
                "macd_signal": t.macd_signal,
                "macd_histogram": t.macd_histogram,
                "bb_upper": t.bb_upper,
                "bb_middle": t.bb_middle,
                "bb_lower": t.bb_lower,
                "sma_20": t.sma_20,
                "sma_50": t.sma_50,
                "sma_200": t.sma_200,
                "adx": t.adx,
                "atr_14": t.atr_14,
            },
            "fundamentals": {
                "market_cap": f.market_cap,
                "pe_ratio": f.pe_ratio,
                "forward_pe": f.forward_pe,
                "peg_ratio": f.peg_ratio,
                "eps_ttm": f.eps_ttm,
                "eps_growth_yoy": f.eps_growth_yoy,
                "revenue_growth_yoy": f.revenue_growth_yoy,
                "profit_margin": f.profit_margin,
                "debt_to_equity": f.debt_to_equity,
                "return_on_equity": f.return_on_equity,
                "beta": f.beta,
                "sector": f.sector,
                "industry": f.industry,
            },
        },
        indent=2,
    )
