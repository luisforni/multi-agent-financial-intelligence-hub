from typing import Any

# Tool definitions in OpenAI / LiteLLM format (compatible with all providers)
SENTIMENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_reddit_sentiment",
            "description": (
                "Retrieves Reddit posts and discussions mentioning the stock ticker or company name "
                "from finance subreddits (r/wallstreetbets, r/stocks, r/investing, etc.) "
                "from the past 7 days. Returns post titles, scores, and text snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    "company_name": {"type": "string", "description": "Full company name"},
                },
                "required": ["ticker", "company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_sentiment",
            "description": (
                "Retrieves recent news articles about the company from financial and mainstream news sources. "
                "Returns article titles, descriptions, and publication dates from the past 7 days."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                    "company_name": {"type": "string", "description": "Full company name"},
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days to look back",
                    },
                },
                "required": ["ticker", "company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fear_greed_index",
            "description": (
                "Retrieves the CNN Fear & Greed Index — a measure of overall market sentiment from 0 (extreme fear) "
                "to 100 (extreme greed). Also returns the index's components and historical trend."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analyst_ratings",
            "description": (
                "Retrieves Wall Street analyst ratings and price targets for the stock: "
                "buy/hold/sell consensus, average target price, and recent rating changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_sentiment_analysis",
            "description": (
                "Submit the final sentiment analysis result. Call this once you have analyzed "
                "all available data sources and formed a comprehensive view of market sentiment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "overall_score": {
                        "type": "number",
                        "description": "Aggregate sentiment score: -1.0 (extremely bearish) to +1.0 (extremely bullish)",
                        "minimum": -1.0,
                        "maximum": 1.0,
                    },
                    "label": {
                        "type": "string",
                        "description": "Sentiment label",
                        "enum": ["VERY_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "VERY_BEARISH"],
                    },
                    "reddit_score": {
                        "type": "number",
                        "description": "Reddit-specific sentiment score (-1 to +1)",
                        "minimum": -1.0,
                        "maximum": 1.0,
                    },
                    "news_score": {
                        "type": "number",
                        "description": "News-specific sentiment score (-1 to +1)",
                        "minimum": -1.0,
                        "maximum": 1.0,
                    },
                    "total_mentions": {
                        "type": "integer",
                        "description": "Total number of mentions analyzed",
                    },
                    "bullish_themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key bullish themes identified (3-5 items)",
                    },
                    "bearish_themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key bearish themes identified (3-5 items)",
                    },
                    "key_catalysts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Near-term catalysts identified from news and social media",
                    },
                    "sentiment_summary": {
                        "type": "string",
                        "description": "Detailed narrative summary of sentiment analysis (2-3 paragraphs)",
                    },
                },
                "required": [
                    "overall_score",
                    "label",
                    "sentiment_summary",
                    "bullish_themes",
                    "bearish_themes",
                ],
            },
        },
    },
]
