from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://options:options_secret@localhost:5432/options_trading"
    POSTGRES_USER: str = "options"
    POSTGRES_PASSWORD: str = "options_secret"
    POSTGRES_DB: str = "options_trading"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLMs
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"          # analysts + risk manager (checklist tasks)
    ANTHROPIC_TRADER_MODEL: str = "claude-sonnet-4-6"   # trader synthesis only (weighs all factors)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.1:8b"
    # Adversary / devil's-advocate model. Recommended (in order):
    #   - "qwq:32b-q3_k_m"     — Alibaba QwQ-32B, reasoning specialist, ~15GB on RTX 5080 (best quality)
    #   - "qwen3:14b-instruct" — Qwen3 instruction-tuned, ~9GB, faster than QwQ-32B
    #   - "deepseek-r1:7b"     — original, ~5GB, weakest reasoning
    # Switch by `ollama pull qwq:32b-q3_k_m` then setting this var.
    OLLAMA_ADVERSARY_MODEL: str = "deepseek-r1:7b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    # Optional GPU-resident heavy lifter — used for batch NLP (8-K classification,
    # transcript embedding, news dedup). When unset, falls back to OLLAMA_CHAT_MODEL.
    OLLAMA_NLP_MODEL: str = "qwen3:14b-instruct"

    # Market data APIs
    # MarketData.app — options data (historical chains supported)
    MARKETDATA_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    FRED_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    FMP_API_KEY: str = ""

    # Twilio (optional)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_TO_NUMBER: str = ""

    # Discord (recommended — free, instant alerts on phone)
    DISCORD_WEBHOOK_URL: str = ""  # Get from Discord: Server Settings → Integrations → Webhooks

    # Auth
    SECRET_KEY: str = "change-this-to-a-random-64-char-string-before-deploy"

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Trading parameters
    MAX_PORTFOLIO_HEAT: float = 0.30
    MAX_SECTOR_CONCENTRATION: float = 0.35
    MAX_NET_DELTA_BIAS: float = 0.60
    POSITION_MONITOR_INTERVAL: int = 900
    STAGE1_MIN_OPTIONS_VOLUME: int = 500_000

    # Options strategy defaults (tastytrade research)
    DIRECTIONAL_DELTA: float = 0.40       # target delta for directional trades
    PREMIUM_SELL_DELTA: float = 0.16      # target delta for premium-selling
    SWING_DTE_MIN: int = 14
    SWING_DTE_MAX: int = 21
    POSITION_DTE_MIN: int = 30
    POSITION_DTE_MAX: int = 60
    PROFIT_TARGET_PCT: float = 0.50       # close at 50% max profit (premium-selling)
    STOP_LOSS_DEBIT_PCT: float = 0.50     # max loss on debit = 50% of debit paid
    STOP_LOSS_CREDIT_MULT: float = 2.0    # max loss on credit = 2x credit received
    ROLL_ALERT_DTE: int = 21              # roll alert when DTE <= this

    # Circuit breaker parameters
    DAILY_LOSS_CAP_PCT: float = 0.05      # halt new trades if daily loss > 5% of portfolio
    MAX_DRAWDOWN_PCT: float = 0.15        # halt if portfolio is down > 15% from peak
    MAX_OPEN_POSITIONS: int = 10          # max concurrent open positions
    PAPER_PORTFOLIO_VALUE: float = 150_000.0  # starting paper portfolio value ($)

    # P0 Stage 1.5 — operating mode gates which signals may feed compute_final_score.
    # backtest: all signals (raw evaluation). paper: only paper/live_small/live_full.
    # live_small: only live_small/live_full. live_full: only live_full. Default paper:
    # the 20 live_full core-engine signals contribute; the 18 'proposed' experimental
    # signals (vrp_z, skew_25d, momentum_12_1, ...) cannot leak into conviction.
    OPERATING_MODE: str = "paper"

    # Position sizing — half-Kelly (professional standard)
    # Full Kelly = max growth but massive drawdown. Half-Kelly = ~75% optimal growth, ~50% less drawdown.
    # Reference: NBER 2025 options sizing research, tastytrade capital allocation research
    KELLY_FRACTION: float = 0.50          # half-Kelly (was 0.25 quarter-Kelly — updated per research)
    BASE_POSITION_SIZE_PCT: float = 0.02  # 2% base size per trade
    MAX_POSITION_SIZE_PCT: float = 0.04   # 4% maximum (conviction-scaled)
    MIN_SIGNALS_REQUIRED: int = 3         # minimum independent category signals before any entry

    # VIX regime thresholds (research-backed from SpotGamma/CBOE/Tastytrade)
    VIX_CALM: float = 15.0      # < 15: directional buys, thin premium
    VIX_NORMAL: float = 20.0    # 15-20: iron condors, calendar spreads
    VIX_ELEVATED: float = 30.0  # 20-30: credit spreads, rich premium
                                 # > 30: crisis — reduce size, hedge only


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
