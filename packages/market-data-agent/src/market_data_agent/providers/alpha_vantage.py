from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider:
    """Alpha Vantage API client for supplemental financial data."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_quote(self, ticker: str) -> dict[str, Any]:
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": ticker,
            "apikey": self._api_key,
        }
        resp = await self._client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("Global Quote", {})

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_company_overview(self, ticker: str) -> dict[str, Any]:
        params = {
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": self._api_key,
        }
        resp = await self._client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_earnings(self, ticker: str) -> dict[str, Any]:
        params = {
            "function": "EARNINGS",
            "symbol": ticker,
            "apikey": self._api_key,
        }
        resp = await self._client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_news_sentiment(self, tickers: str) -> dict[str, Any]:
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": tickers,
            "apikey": self._api_key,
            "limit": "50",
        }
        resp = await self._client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()
