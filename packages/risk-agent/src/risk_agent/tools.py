from typing import Any

# Tool definitions in OpenAI / LiteLLM format (compatible with all providers)
RISK_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_quantitative_risk_metrics",
            "description": (
                "Computes comprehensive quantitative risk metrics from 2 years of historical price data: "
                "30d and 90d historical volatility, VaR at 95%/99%, Expected Shortfall (CVaR), "
                "Beta vs S&P 500, Sharpe ratio, Sortino ratio, Max Drawdown, and Calmar ratio."
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
            "name": "get_market_data_summary",
            "description": "Retrieves the pre-computed market data and technical/fundamental analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sentiment_summary",
            "description": "Retrieves the pre-computed sentiment analysis results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart_analysis",
            "description": (
                "Retrieves the pre-computed chart vision analysis including trend, chart patterns "
                "(head & shoulders, double top/bottom, triangles, flags, etc.), support/resistance levels, "
                "and the chart-based signal (BUY/SELL/HOLD). Incorporate this into your final recommendation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_position_sizing",
            "description": (
                "Computes optimal position sizing using ATR-based stop loss and Kelly criterion. "
                "Returns recommended shares, notional value, stop loss price, and portfolio allocation %."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "signal_direction": {
                        "type": "string",
                        "enum": ["bullish", "bearish"],
                        "description": "Direction of the trade signal",
                    },
                    "portfolio_value": {
                        "type": "number",
                        "description": "Assumed portfolio value in USD (default: 100000)",
                    },
                },
                "required": ["ticker", "signal_direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_recommendation",
            "description": (
                "Submit the final investment recommendation. Call this after you have analyzed "
                "all risk metrics, market data, and sentiment to form a high-conviction view."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "signal": {
                        "type": "string",
                        "enum": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"],
                        "description": "Investment signal",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level (0.0 to 1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH"],
                        "description": "Overall risk classification",
                    },
                    "time_horizon_days": {
                        "type": "integer",
                        "description": "Recommended holding period in days",
                    },
                    "target_price_bull": {"type": "number", "description": "Bull case price target"},
                    "target_price_base": {"type": "number", "description": "Base case price target"},
                    "target_price_bear": {"type": "number", "description": "Bear case price target"},
                    "stop_loss": {"type": "number", "description": "Recommended stop loss price"},
                    "technical_score": {
                        "type": "number",
                        "description": "Technical analysis score 0-100",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "fundamental_score": {
                        "type": "number",
                        "description": "Fundamental quality score 0-100",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "sentiment_score": {
                        "type": "number",
                        "description": "Sentiment score 0-100",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "risk_adjusted_score": {
                        "type": "number",
                        "description": "Composite risk-adjusted score 0-100",
                        "minimum": 0,
                        "maximum": 100,
                    },
                    "executive_summary": {
                        "type": "string",
                        "description": "2-3 sentence executive summary of the recommendation",
                    },
                    "bull_case": {
                        "type": "string",
                        "description": "Bull case scenario description (2-3 sentences)",
                    },
                    "bear_case": {
                        "type": "string",
                        "description": "Bear case scenario description (2-3 sentences)",
                    },
                    "key_risks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Top 3-5 key risks",
                    },
                    "key_catalysts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Top 3-5 near-term catalysts",
                    },
                },
                "required": [
                    "signal",
                    "confidence",
                    "risk_level",
                    "executive_summary",
                    "bull_case",
                    "bear_case",
                    "key_risks",
                    "key_catalysts",
                ],
            },
        },
    },
]
