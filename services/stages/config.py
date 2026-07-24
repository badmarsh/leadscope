"""
config.py — centralised env-var loading for the stages service.
All keys read from .env via python-dotenv.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope@localhost:5432/leadscope")

# ── LLM providers ────────────────────────────────────────────────────────────
GEMINI_PROXY_API_KEY: str = os.environ.get("GEMINI_PROXY_API_KEY", "")
GEMINI_PROXY_ENDPOINT: str = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://127.0.0.1:8045")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")

# Gemini model string as exposed by the local proxy.
# Use gemini-3.6-flash-high for the general fallback.
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash-high")

# Per-task model overrides — each call site has different complexity requirements
STAGE1_MODEL: str = os.environ.get("STAGE1_MODEL", "gemini-3.1-pro-low")        # ICP generation — foundational, run once, worth Pro quality
STAGE2_DEDUP_MODEL: str = os.environ.get("STAGE2_DEDUP_MODEL", "gemini-3.1-flash-lite")  # search result dedup — pure list filtering
STAGE5_MODEL: str = os.environ.get("STAGE5_MODEL", "gemini-3.6-flash-low")      # enrichment extraction + Slovak sentence
KB_INGEST_MODEL: str = os.environ.get("KB_INGEST_MODEL", "gemini-3.6-flash-medium")  # malware signature extraction from 15k articles
SCORER_TEXT_MODEL: str = os.environ.get("SCORER_TEXT_MODEL", "gemini-3.6-flash-high")
SCORER_VISION_MODEL: str = os.environ.get("SCORER_VISION_MODEL", "gemini-3.1-pro")

OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3")

# ── Firecrawl ────────────────────────────────────────────────────────────────
FIRECRAWL_ENDPOINT: str = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
# Search & Data Providers
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

# ── Crawler service (Crawl4AI — self-hosted, replaces Firecrawl for enrichment) ──
CRAWLER_ENDPOINT: str = os.environ.get("CRAWLER_ENDPOINT", "http://crawler:8003")

# ── Search APIs ──────────────────────────────────────────────────────────────
EXA_API_KEY: str = os.environ.get("EXA_API_KEY", "")
TAVILY_API_KEY: str = os.environ.get("TAVILY_API_KEY", "")
SERPER_API_KEY: str = os.environ.get("SERPER_API_KEY", "")
SERPAPI_API_KEY: str = os.environ.get("SERPAPI_API_KEY", "")
BRAVE_SEARCH_API_KEY: str = os.environ.get("BRAVE_SEARCH_API_KEY", "")
PUBLICWWW_API_KEY: str = os.environ.get("PUBLICWWW_API_KEY", "")
URLSCAN_API_KEY: str = os.environ.get("URLSCAN_API_KEY", "")
NETLAS_API_KEY: str = os.environ.get("NETLAS_API_KEY", "")
AHREFS_API_KEY: str = os.environ.get("AHREFS_API_KEY", "")
VIRUSTOTAL_API_KEY: str = os.environ.get("VIRUSTOTAL_API_KEY", "")
HUNTER_API_KEY: str = os.environ.get("HUNTER_API_KEY", "")

# ── Tuning constants ──────────────────────────────────────────────────────────
MAX_ENRICHMENT_ATTEMPTS: int = int(os.environ.get("MAX_ENRICHMENT_ATTEMPTS", "3"))
ENRICHMENT_RETRY_HOURS: int = int(os.environ.get("ENRICHMENT_RETRY_HOURS", "24"))
# Minimum hits before moving to next provider in keyword-search waterfall
KEYWORD_MIN_HITS: int = int(os.environ.get("KEYWORD_MIN_HITS", "5"))
# Cooldown window for stale-candidate reopen (days)
STALE_REOPEN_DAYS: int = int(os.environ.get("STALE_REOPEN_DAYS", "90"))
# Days before re-running the exact same search query (overridable via campaign settings UI)
SEARCH_COOLDOWN_DAYS: int = int(os.environ.get("SEARCH_COOLDOWN_DAYS", "30"))

# ── Cost-estimate pricing map (USD per unit) ──────────────────────────────────
# Update these periodically as provider pricing changes — see §0.4 staleness caveat.
# Gemini 2.5 Flash pricing (per token at 2024 rates):
PRICING_MAP = {
    "gemini": {"input_per_token": 0.075 / 1_000_000, "output_per_token": 0.30 / 1_000_000},
    "openrouter": {"input_per_token": 0.003 / 1_000, "output_per_token": 0.015 / 1_000},
    "exa": {"per_query": 0.005},
    "tavily": {"per_query": 0.004},
    "serper": {"per_query": 0.001},
    "serpapi": {"per_query": 0.001},
    "brave": {"per_query": 0.001},
    "publicwww": {"per_query": 0.0},   # quota-based, no marginal USD cost
    "firecrawl": {"per_query": 0.0},   # self-hosted (legacy — being phased out)
    "crawler": {"per_query": 0.0},     # self-hosted Crawl4AI service
    "ollama": {"per_query": 0.0},      # local
    "urlhaus": {"per_query": 0.0},     # free API
    "urlscan": {"per_query": 0.0},     # free tier
    "certstream": {"per_query": 0.0},  # free WebSocket feed
}
