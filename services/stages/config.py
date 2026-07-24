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
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash-high")

# Per-task model overrides
STAGE1_MODEL: str = os.environ.get("STAGE1_MODEL", "gemini-3.1-pro-low")
STAGE2_DEDUP_MODEL: str = os.environ.get("STAGE2_DEDUP_MODEL", "gemini-3.1-flash-lite")
STAGE5_MODEL: str = os.environ.get("STAGE5_MODEL", "gemini-3.6-flash-low")
KB_INGEST_MODEL: str = os.environ.get("KB_INGEST_MODEL", "gemini-3.6-flash-medium")
SCORER_TEXT_MODEL: str = os.environ.get("SCORER_TEXT_MODEL", "gemini-3.6-flash-high")
SCORER_VISION_MODEL: str = os.environ.get("SCORER_VISION_MODEL", "gemini-3.1-pro")

OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3")

# ── Firecrawl ────────────────────────────────────────────────────────────────
FIRECRAWL_ENDPOINT: str = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

# ── Crawler service (Crawl4AI — self-hosted) ─────────────────────────────────
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
SHODAN_API_KEY: str = os.environ.get("SHODAN_API_KEY", "")

# ── Contact enrichment ────────────────────────────────────────────────────────
# Apollo.io People Search — person-level contacts with job titles + LinkedIn URLs
APOLLO_API_KEY: str = os.environ.get("APOLLO_API_KEY", "")
# Set to "false" to skip Hunter email verification (saves API credits)
HUNTER_VERIFY_CONTACTS: bool = os.environ.get("HUNTER_VERIFY_CONTACTS", "true").lower() == "true"

# ── Tuning constants ──────────────────────────────────────────────────────────
MAX_ENRICHMENT_ATTEMPTS: int = int(os.environ.get("MAX_ENRICHMENT_ATTEMPTS", "3"))
ENRICHMENT_RETRY_HOURS: int = int(os.environ.get("ENRICHMENT_RETRY_HOURS", "24"))
KEYWORD_MIN_HITS: int = int(os.environ.get("KEYWORD_MIN_HITS", "5"))
STALE_REOPEN_DAYS: int = int(os.environ.get("STALE_REOPEN_DAYS", "90"))
SEARCH_COOLDOWN_DAYS: int = int(os.environ.get("SEARCH_COOLDOWN_DAYS", "30"))

# ── Cost-estimate pricing map (USD per unit) ──────────────────────────────────
PRICING_MAP = {
    "gemini": {"input_per_token": 0.075 / 1_000_000, "output_per_token": 0.30 / 1_000_000},
    "openrouter": {"input_per_token": 0.003 / 1_000, "output_per_token": 0.015 / 1_000},
    "exa": {"per_query": 0.005},
    "tavily": {"per_query": 0.004},
    "serper": {"per_query": 0.001},
    "serpapi": {"per_query": 0.001},
    "brave": {"per_query": 0.001},
    "publicwww": {"per_query": 0.0},
    "firecrawl": {"per_query": 0.0},
    "crawler": {"per_query": 0.0},
    "ollama": {"per_query": 0.0},
    "urlhaus": {"per_query": 0.0},
    "urlscan": {"per_query": 0.0},
    "certstream": {"per_query": 0.0},
    "apollo": {"per_query": 0.0},   # credit-based; no USD marginal cost tracked here
    "shodan": {"per_query": 0.0},   # query-credit-based
    "malwarebazaar": {"per_query": 0.0},  # free API
}

# ── Few-shot calibration ─────────────────────────────────────────────────────
FEW_SHOT_K: int = int(os.environ.get("FEW_SHOT_K", "5"))
