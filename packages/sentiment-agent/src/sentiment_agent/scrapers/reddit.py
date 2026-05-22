from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_FINANCE_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "SecurityAnalysis",
    "StockMarket",
    "options",
]


@dataclass
class RedditPost:
    subreddit: str
    title: str
    text: str
    score: int
    upvote_ratio: float
    num_comments: int
    url: str
    created_utc: float


class RedditScraper:
    """Scrapes Reddit for stock mentions using PRAW."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent
        self._reddit: Any = None

    def _get_reddit(self) -> Any:
        if self._reddit is None:
            import praw  # lazy import — not everyone has PRAW configured

            self._reddit = praw.Reddit(
                client_id=self._client_id,
                client_secret=self._client_secret,
                user_agent=self._user_agent,
            )
        return self._reddit

    async def search_ticker(
        self,
        ticker: str,
        company_name: str,
        limit_per_sub: int = 20,
    ) -> list[RedditPost]:
        if not self._client_id or not self._client_secret:
            logger.warning("Reddit credentials not configured; skipping")
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_search,
            ticker,
            company_name,
            limit_per_sub,
        )

    def _sync_search(
        self, ticker: str, company_name: str, limit_per_sub: int
    ) -> list[RedditPost]:
        reddit = self._get_reddit()
        posts: list[RedditPost] = []
        query = f"{ticker} OR {company_name}"

        for sub_name in _FINANCE_SUBREDDITS:
            try:
                subreddit = reddit.subreddit(sub_name)
                for submission in subreddit.search(query, limit=limit_per_sub, time_filter="week"):
                    posts.append(
                        RedditPost(
                            subreddit=sub_name,
                            title=submission.title,
                            text=submission.selftext[:500] if submission.selftext else "",
                            score=submission.score,
                            upvote_ratio=submission.upvote_ratio,
                            num_comments=submission.num_comments,
                            url=submission.url,
                            created_utc=submission.created_utc,
                        )
                    )
            except Exception as exc:
                logger.warning(
                    "Reddit search failed for subreddit",
                    extra={"subreddit": sub_name, "error": str(exc)},
                )

        return sorted(posts, key=lambda p: p.score, reverse=True)

    def format_for_analysis(self, posts: list[RedditPost]) -> list[dict[str, str]]:
        return [
            {
                "source": f"r/{p.subreddit}",
                "title": p.title,
                "text": p.text[:300] if p.text else "",
                "score": str(p.score),
                "comments": str(p.num_comments),
            }
            for p in posts[:30]
        ]
