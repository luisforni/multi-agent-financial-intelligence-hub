from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    title: str
    description: str
    source: str
    url: str
    published_at: str
    content_snippet: str = ""


class NewsScraper:
    """Fetches financial news from NewsAPI and other public sources."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def search_news(
        self,
        ticker: str,
        company_name: str,
        days_back: int = 7,
    ) -> list[NewsArticle]:
        if not self._api_key:
            logger.warning("NewsAPI key not configured; skipping")
            return []

        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        articles: list[NewsArticle] = []

        # Search by ticker
        for query in [ticker, company_name]:
            try:
                resp = await self._client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "from": from_date,
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": 25,
                        "apiKey": self._api_key,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("articles", []):
                        articles.append(
                            NewsArticle(
                                title=item.get("title") or "",
                                description=item.get("description") or "",
                                source=item.get("source", {}).get("name", "Unknown"),
                                url=item.get("url", ""),
                                published_at=item.get("publishedAt", ""),
                                content_snippet=(item.get("content") or "")[:300],
                            )
                        )
            except Exception as exc:
                logger.warning("News fetch failed", extra={"query": query, "error": str(exc)})

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[NewsArticle] = []
        for art in articles:
            if art.url not in seen:
                seen.add(art.url)
                unique.append(art)

        return unique[:50]

    def format_for_analysis(self, articles: list[NewsArticle]) -> list[dict[str, str]]:
        return [
            {
                "source": a.source,
                "title": a.title,
                "description": a.description[:300],
                "published_at": a.published_at,
            }
            for a in articles[:25]
        ]
