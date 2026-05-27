from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM Provider — default: Ollama (local, no API key required)
    # Supported values: ollama, anthropic, openai, gemini, groq, mistral, together
    # When running via Docker Compose use LLM_BASE_URL=http://host.docker.internal:11434
    # When running locally (uv/pip) use LLM_BASE_URL=http://localhost:11434
    llm_provider: str = Field("ollama", alias="LLM_PROVIDER")
    llm_base_url: str = Field("http://localhost:11434", alias="LLM_BASE_URL")

    # API keys — set only the provider(s) you intend to use
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    groq_api_key: str = Field("", alias="GROQ_API_KEY")
    mistral_api_key: str = Field("", alias="MISTRAL_API_KEY")
    together_api_key: str = Field("", alias="TOGETHER_API_KEY")

    # Market data
    alpha_vantage_api_key: str = Field("", alias="ALPHA_VANTAGE_API_KEY")
    polygon_api_key: str = Field("", alias="POLYGON_API_KEY")

    # Social / news
    reddit_client_id: str = Field("", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field("", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field("FinancialIntelligenceHub/1.0", alias="REDDIT_USER_AGENT")
    news_api_key: str = Field("", alias="NEWS_API_KEY")

    # Infrastructure
    redis_url: str = Field("redis://localhost:6379", alias="REDIS_URL")
    postgres_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/fintelligence",
        alias="POSTGRES_URL",
    )

    # Alpaca trading
    alpaca_mode: str = Field("", alias="ALPACA_MODE")       # "paper" | "live" | "" (disabled)
    alpaca_api_key: str = Field("", alias="ALPACA_API_KEY")
    alpaca_api_secret: str = Field("", alias="ALPACA_API_SECRET")

    @property
    def alpaca_enabled(self) -> bool:
        return bool(self.alpaca_mode and self.alpaca_api_key and self.alpaca_api_secret)

    @property
    def alpaca_base_url(self) -> str:
        return (
            "https://paper-api.alpaca.markets"
            if self.alpaca_mode == "paper"
            else "https://api.alpaca.markets"
        )

    # Application
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    environment: str = Field("development", alias="ENVIRONMENT")
    max_analysis_timeout_seconds: int = Field(120, alias="MAX_ANALYSIS_TIMEOUT_SECONDS")

    # Chart vision model — set to a vision-capable model to enable image-based chart analysis.
    # Vision models: ollama/llava  |  openai/gpt-4o  |  gemini/gemini-1.5-flash
    # If empty, the chart agent falls back to text-based analysis (works with any LLM).
    chart_vision_model: str = Field("", alias="CHART_VISION_MODEL")

    # Scanner settings
    scanner_interval_seconds: int = Field(300, alias="SCANNER_INTERVAL_SECONDS")
    scanner_signal_threshold: float = Field(0.5, alias="SCANNER_SIGNAL_THRESHOLD")

    # Agent models — defaults use Ollama llama3.2 for local-first, zero-cost operation.
    # Override with provider-prefixed model names, e.g.:
    #   Ollama:     ollama/llama3.2  ollama/mistral  ollama/qwen2.5
    #   Anthropic:  anthropic/claude-sonnet-4-6  anthropic/claude-opus-4-7
    #   OpenAI:     openai/gpt-4o  openai/gpt-4o-mini
    #   Gemini:     gemini/gemini-1.5-flash  gemini/gemini-1.5-pro
    #   Groq:       groq/llama-3.3-70b-versatile  groq/mixtral-8x7b-32768
    #   Mistral:    mistral/mistral-large-latest  mistral/mistral-small-latest
    market_data_agent_model: str = Field("ollama/llama3.2", alias="MARKET_DATA_AGENT_MODEL")
    sentiment_agent_model: str = Field("ollama/llama3.2", alias="SENTIMENT_AGENT_MODEL")
    risk_agent_model: str = Field("ollama/llama3.2:1b", alias="RISK_AGENT_MODEL")
    risk_agent_fallbacks: str = Field("", alias="RISK_AGENT_FALLBACKS")  # comma-separated

    @property
    def risk_agent_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.risk_agent_fallbacks.split(",") if m.strip()]

    # Portfolio & risk management
    initial_balance: float = Field(10_000.0, alias="INITIAL_BALANCE")
    min_position_usd: float = Field(100.0, alias="MIN_POSITION_USD")
    max_positions_cap: int = Field(50, alias="MAX_POSITIONS_CAP")
    max_drawdown_pct: float = Field(0.20, alias="MAX_DRAWDOWN_PCT")
    trading_hours_only: bool = Field(False, alias="TRADING_HOURS_ONLY")

    # Trading safeguards
    max_day_trades: int = Field(3, alias="MAX_DAY_TRADES")          # PDT: max day trades per 5 business days
    min_hold_days: int = Field(1, alias="MIN_HOLD_DAYS")             # Minimum days before allowing signal reversal
    slippage_pct: float = Field(0.001, alias="SLIPPAGE_PCT")         # Bid/ask spread simulation (0.1%)
    settlement_days: int = Field(2, alias="SETTLEMENT_DAYS")         # T+2 cash settlement

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
