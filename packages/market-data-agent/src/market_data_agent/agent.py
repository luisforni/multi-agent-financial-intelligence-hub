from __future__ import annotations

import json
import logging
import time
from typing import Any

import litellm

from shared.config import Settings
from shared.llm_client import get_completion_kwargs, tool_call_to_dict
from shared.models import StockData

from market_data_agent.providers.yahoo_finance import YahooFinanceProvider
from market_data_agent.providers.alpha_vantage import AlphaVantageProvider
from market_data_agent.tools import MARKET_DATA_TOOLS, format_stock_data_for_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert quantitative analyst and financial data specialist.
Your role is to gather, validate, and interpret real-time market data for a given stock.

Your analysis must cover:
1. **Price action**: Current price, day range, 52-week range, momentum
2. **Technical indicators**: RSI (overbought/oversold), MACD (momentum direction), \
Bollinger Bands (volatility), moving averages (trend), ADX (trend strength), ATR (volatility)
3. **Volume analysis**: Compare current vs average volume; institutional accumulation/distribution
4. **Fundamental metrics**: Valuation ratios (P/E, PEG, P/B), growth rates, profitability, \
balance sheet health, competitive moat
5. **Market context**: Sector/index relative performance

Use the available tools to collect data, then call `submit_market_analysis` with your synthesis.
Be precise, data-driven, and objective. Identify both strengths and weaknesses.
"""


class MarketDataAgent:
    """
    Agentic financial data extractor powered by any LiteLLM-compatible provider.

    Uses tool-use to autonomously fetch and synthesize price data,
    technical indicators, and fundamental metrics.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.market_data_agent_model
        self._completion_kwargs = get_completion_kwargs(settings, self._model)
        self._yf_provider = YahooFinanceProvider()
        self._av_provider = (
            AlphaVantageProvider(settings.alpha_vantage_api_key)
            if settings.alpha_vantage_api_key
            else None
        )

    async def analyze(self, ticker: str) -> StockData:
        """Run the full agentic analysis loop for a ticker."""
        ticker = ticker.upper().strip()
        logger.info("MarketDataAgent starting analysis", extra={"ticker": ticker})
        start = time.monotonic()

        stock_data = await self._yf_provider.get_stock_data(ticker)
        options_flow = await self._get_options_flow(ticker)
        market_ctx = await self._get_market_context(ticker)

        tool_cache: dict[str, Any] = {
            "stock_data": stock_data,
            "options_flow": options_flow,
            "market_context": market_ctx,
        }

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Perform a comprehensive market data analysis for **{ticker}** "
                    f"({stock_data.company_name}). "
                    f"Use all available tools to gather complete data, then submit your analysis."
                ),
            },
        ]

        analysis_result: dict[str, Any] | None = None

        while True:
            response = await litellm.acompletion(
                model=self._model,
                max_tokens=4096,
                messages=messages,
                tools=MARKET_DATA_TOOLS,
                **self._completion_kwargs,
            )

            choice = response.choices[0]
            logger.debug(
                "LLM response",
                extra={"finish_reason": choice.finish_reason, "model": self._model},
            )

            if choice.finish_reason == "stop":
                break

            tool_calls = getattr(choice.message, "tool_calls", None) or []
            if not tool_calls:
                break

            # Append assistant turn with its tool calls
            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [tool_call_to_dict(tc) for tc in tool_calls],
            })

            # Execute each tool and append results
            for tc in tool_calls:
                tool_name = tc.function.name
                tool_input: dict[str, Any] = json.loads(tc.function.arguments)

                tool_result = await self._execute_tool(tool_name, tool_input, tool_cache)

                if tool_name == "submit_market_analysis":
                    analysis_result = tool_input

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result),
                })

            if analysis_result is not None:
                break

        if analysis_result:
            stock_data.technical_summary = analysis_result.get("technical_summary")
            stock_data.fundamental_summary = analysis_result.get("fundamental_summary")

        duration = time.monotonic() - start
        logger.info(
            "MarketDataAgent analysis complete",
            extra={"ticker": ticker, "duration_s": round(duration, 2)},
        )
        return stock_data

    async def _execute_tool(
        self, name: str, input_data: dict[str, Any], cache: dict[str, Any]
    ) -> dict[str, Any]:
        logger.debug("Executing tool", extra={"tool": name})

        if name == "get_stock_price_and_technicals":
            stock: StockData = cache["stock_data"]
            return json.loads(format_stock_data_for_tool(stock))

        if name == "get_company_fundamentals":
            stock = cache["stock_data"]
            f = stock.fundamentals
            return {
                "ticker": stock.ticker,
                "company": stock.company_name,
                "sector": f.sector,
                "industry": f.industry,
                "market_cap": f.market_cap,
                "pe_ratio": f.pe_ratio,
                "forward_pe": f.forward_pe,
                "peg_ratio": f.peg_ratio,
                "price_to_book": f.price_to_book,
                "price_to_sales": f.price_to_sales,
                "ev_to_ebitda": f.ev_to_ebitda,
                "eps_ttm": f.eps_ttm,
                "eps_growth_yoy": f.eps_growth_yoy,
                "revenue_growth_yoy": f.revenue_growth_yoy,
                "profit_margin": f.profit_margin,
                "debt_to_equity": f.debt_to_equity,
                "current_ratio": f.current_ratio,
                "quick_ratio": f.quick_ratio,
                "roe": f.return_on_equity,
                "roa": f.return_on_assets,
                "dividend_yield": f.dividend_yield,
                "beta": f.beta,
                "short_ratio": f.short_ratio,
            }

        if name == "get_options_flow_summary":
            return cache.get("options_flow", {"error": "Options data not available"})

        if name == "get_market_context":
            return cache.get("market_context", {"error": "Market context not available"})

        if name == "submit_market_analysis":
            return {"status": "submitted", "message": "Analysis recorded successfully"}

        return {"error": f"Unknown tool: {name}"}

    async def _get_options_flow(self, ticker: str) -> dict[str, Any]:
        """Fetch options data from Yahoo Finance."""
        try:
            import asyncio
            import yfinance as yf

            loop = asyncio.get_event_loop()

            def _fetch() -> dict[str, Any]:
                yf_ticker = yf.Ticker(ticker)
                expiries = yf_ticker.options
                if not expiries:
                    return {"error": "No options data"}
                expiry = expiries[min(2, len(expiries) - 1)]
                chain = yf_ticker.option_chain(expiry)
                calls_volume = int(chain.calls["volume"].sum())
                puts_volume = int(chain.puts["volume"].sum())
                pc_ratio = puts_volume / max(calls_volume, 1)
                avg_iv_calls = float(chain.calls["impliedVolatility"].median())
                avg_iv_puts = float(chain.puts["impliedVolatility"].median())
                return {
                    "expiry": expiry,
                    "calls_volume": calls_volume,
                    "puts_volume": puts_volume,
                    "put_call_ratio": round(pc_ratio, 3),
                    "avg_iv_calls": round(avg_iv_calls, 4),
                    "avg_iv_puts": round(avg_iv_puts, 4),
                    "avg_iv": round((avg_iv_calls + avg_iv_puts) / 2, 4),
                }

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.warning("Options data fetch failed", extra={"ticker": ticker, "error": str(exc)})
            return {"error": str(exc)}

    async def _get_market_context(self, ticker: str) -> dict[str, Any]:
        """Fetch SPY/VIX and sector context."""
        try:
            import asyncio
            import yfinance as yf

            loop = asyncio.get_event_loop()

            def _fetch() -> dict[str, Any]:
                spy = yf.Ticker("SPY").history(period="1mo")
                vix = yf.Ticker("^VIX").history(period="5d")
                stock_hist = yf.Ticker(ticker).history(period="1mo")

                spy_ret = float((spy["Close"].iloc[-1] / spy["Close"].iloc[0] - 1) * 100)
                vix_level = float(vix["Close"].iloc[-1])
                stock_ret = float((stock_hist["Close"].iloc[-1] / stock_hist["Close"].iloc[0] - 1) * 100)
                relative_strength = round(stock_ret - spy_ret, 2)

                return {
                    "spy_1m_return_pct": round(spy_ret, 2),
                    "vix_level": round(vix_level, 2),
                    "stock_1m_return_pct": round(stock_ret, 2),
                    "relative_strength_vs_spy": relative_strength,
                    "market_regime": (
                        "risk-off" if vix_level > 25
                        else "elevated_volatility" if vix_level > 18
                        else "normal"
                    ),
                }

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.warning("Market context fetch failed", extra={"ticker": ticker, "error": str(exc)})
            return {"error": str(exc)}

    async def close(self) -> None:
        if self._av_provider:
            await self._av_provider.close()
