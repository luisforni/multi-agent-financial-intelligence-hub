from __future__ import annotations

import json
import logging
import time
from typing import Any

import litellm

from shared.config import Settings
from shared.llm_client import get_completion_kwargs, tool_call_to_dict
from shared.models import SentimentData, SentimentLabel, SentimentSource, StockData

from sentiment_agent.scrapers.reddit import RedditScraper
from sentiment_agent.scrapers.news import NewsScraper
from sentiment_agent.tools import SENTIMENT_TOOLS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a sophisticated financial sentiment analyst specializing in retail and institutional investor sentiment.

Your mission is to analyze sentiment across all available data sources — social media (Reddit), \
financial news, and market indicators — for a given stock, and produce a nuanced, actionable sentiment report.

Analysis framework:
1. **Volume & Velocity**: How much discussion is happening, and is it increasing?
2. **Tone & Conviction**: Distinguish casual mentions from high-conviction bullish/bearish arguments
3. **Theme Identification**: Extract recurring bullish/bearish narratives (earnings expectations, \
product launches, regulatory risks, competitive threats, macro tailwinds/headwinds)
4. **Source Credibility Weighting**: Institutional analysis > financial news > informed Reddit > retail chatter
5. **Contrarian Signals**: Extreme sentiment (euphoria or despair) often precedes reversals
6. **Catalyst Identification**: Near-term events (earnings, product launches, regulatory decisions) \
mentioned in the data

Use all available tools, then call `submit_sentiment_analysis` with your comprehensive assessment.
Be nuanced — distinguish between signal and noise. Provide specific evidence for your conclusions.
"""


class SentimentAgent:
    """
    Agentic sentiment analyzer powered by any LiteLLM-compatible provider.

    Scrapes Reddit, news, and market indicators, then uses the configured LLM
    to synthesize a nuanced sentiment score with themes and catalysts.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.sentiment_agent_model
        self._completion_kwargs = get_completion_kwargs(settings, self._model)
        self._reddit = RedditScraper(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )
        self._news = NewsScraper(api_key=settings.news_api_key)

    async def analyze(self, ticker: str, company_name: str) -> SentimentData:
        ticker = ticker.upper().strip()
        logger.info("SentimentAgent starting analysis", extra={"ticker": ticker})
        start = time.monotonic()

        reddit_posts = await self._reddit.search_ticker(ticker, company_name)
        news_articles = await self._news.search_news(ticker, company_name)
        analyst_ratings = await self._get_analyst_ratings(ticker)
        fear_greed = await self._get_fear_greed_index()

        cache: dict[str, Any] = {
            "reddit_posts": reddit_posts,
            "news_articles": news_articles,
            "analyst_ratings": analyst_ratings,
            "fear_greed": fear_greed,
        }

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Perform a comprehensive sentiment analysis for **{ticker}** ({company_name}). "
                    f"I have data from Reddit ({len(reddit_posts)} posts) and "
                    f"news ({len(news_articles)} articles) ready for your retrieval. "
                    f"Analyze all sources and submit your final sentiment assessment."
                ),
            },
        ]

        analysis_result: dict[str, Any] | None = None

        while True:
            response = await litellm.acompletion(
                model=self._model,
                max_tokens=4096,
                messages=messages,
                tools=SENTIMENT_TOOLS,
                **self._completion_kwargs,
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop":
                break

            tool_calls = getattr(choice.message, "tool_calls", None) or []
            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [tool_call_to_dict(tc) for tc in tool_calls],
            })

            for tc in tool_calls:
                tool_name = tc.function.name
                tool_input: dict[str, Any] = json.loads(tc.function.arguments)

                result = await self._execute_tool(
                    tool_name, tool_input, ticker, company_name, cache
                )

                if tool_name == "submit_sentiment_analysis":
                    analysis_result = tool_input

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

            if analysis_result is not None:
                break

        sentiment = self._build_sentiment_data(
            ticker=ticker,
            company_name=company_name,
            analysis_result=analysis_result or {},
            reddit_posts=reddit_posts,
            news_articles=news_articles,
        )

        duration = time.monotonic() - start
        logger.info(
            "SentimentAgent analysis complete",
            extra={
                "ticker": ticker,
                "score": sentiment.overall_score,
                "label": sentiment.label,
                "duration_s": round(duration, 2),
            },
        )
        return sentiment

    async def _execute_tool(
        self,
        name: str,
        input_data: dict[str, Any],
        ticker: str,
        company_name: str,
        cache: dict[str, Any],
    ) -> Any:
        logger.debug("Executing tool", extra={"tool": name})

        if name == "get_reddit_sentiment":
            posts = cache["reddit_posts"]
            return {
                "post_count": len(posts),
                "posts": self._reddit.format_for_analysis(posts),
            }

        if name == "get_news_sentiment":
            articles = cache["news_articles"]
            return {
                "article_count": len(articles),
                "articles": self._news.format_for_analysis(articles),
            }

        if name == "get_fear_greed_index":
            return cache.get("fear_greed", {"error": "Not available"})

        if name == "get_analyst_ratings":
            return cache.get("analyst_ratings", {"error": "Not available"})

        if name == "submit_sentiment_analysis":
            return {"status": "submitted"}

        return {"error": f"Unknown tool: {name}"}

    def _build_sentiment_data(
        self,
        ticker: str,
        company_name: str,
        analysis_result: dict[str, Any],
        reddit_posts: list[Any],
        news_articles: list[Any],
    ) -> SentimentData:
        label_str = analysis_result.get("label", "NEUTRAL")
        try:
            label = SentimentLabel(label_str)
        except ValueError:
            label = SentimentLabel.NEUTRAL

        sources = []
        if reddit_posts:
            sources.append(
                SentimentSource(
                    source="Reddit",
                    mention_count=len(reddit_posts),
                    avg_score=analysis_result.get("reddit_score", 0.0),
                    sample_texts=[p.title for p in reddit_posts[:3]],
                )
            )
        if news_articles:
            sources.append(
                SentimentSource(
                    source="NewsAPI",
                    mention_count=len(news_articles),
                    avg_score=analysis_result.get("news_score", 0.0),
                    sample_texts=[a.title for a in news_articles[:3]],
                )
            )

        return SentimentData(
            ticker=ticker,
            company_name=company_name,
            overall_score=analysis_result.get("overall_score", 0.0),
            reddit_score=analysis_result.get("reddit_score"),
            news_score=analysis_result.get("news_score"),
            label=label,
            sources=sources,
            total_mentions=analysis_result.get("total_mentions", len(reddit_posts) + len(news_articles)),
            articles_analyzed=len(news_articles),
            bullish_themes=analysis_result.get("bullish_themes", []),
            bearish_themes=analysis_result.get("bearish_themes", []),
            key_catalysts=analysis_result.get("key_catalysts", []),
            sentiment_summary=analysis_result.get("sentiment_summary"),
        )

    async def _get_fear_greed_index(self) -> dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
                if resp.status_code == 200:
                    data = resp.json()
                    fg = data.get("fear_and_greed", {})
                    return {
                        "score": fg.get("score"),
                        "rating": fg.get("rating"),
                        "previous_close": fg.get("previous_close"),
                        "one_week_ago": fg.get("one_week_ago"),
                        "one_month_ago": fg.get("one_month_ago"),
                    }
        except Exception as exc:
            logger.debug("Fear/Greed index fetch failed", extra={"error": str(exc)})
        return {"error": "Fear & Greed index not available"}

    async def _get_analyst_ratings(self, ticker: str) -> dict[str, Any]:
        try:
            import asyncio
            import yfinance as yf

            loop = asyncio.get_event_loop()

            def _fetch() -> dict[str, Any]:
                yf_ticker = yf.Ticker(ticker)
                info = yf_ticker.info or {}
                recs = yf_ticker.recommendations
                result: dict[str, Any] = {
                    "target_mean_price": info.get("targetMeanPrice"),
                    "target_high_price": info.get("targetHighPrice"),
                    "target_low_price": info.get("targetLowPrice"),
                    "recommendation_mean": info.get("recommendationMean"),
                    "recommendation_key": info.get("recommendationKey"),
                    "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),
                }
                if recs is not None and not recs.empty:
                    recent = recs.tail(10)
                    result["recent_ratings"] = recent.to_dict(orient="records")
                return result

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.debug("Analyst ratings fetch failed", extra={"error": str(exc)})
            return {"error": str(exc)}

    async def close(self) -> None:
        await self._news.close()
