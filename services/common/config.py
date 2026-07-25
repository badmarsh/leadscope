"""
config.py — Centralised env-var loading for the leadscope pipeline.
"""
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
# Evaluator enforces presence, stages had a default with dev credentials.
# We enforce presence to prevent silent fallback to dev credentials in prod.
DATABASE_URL: str = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise KeyError("DATABASE_URL must be set in .env")

# ── LLM providers ────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL: str = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

GEMINI_PROXY_API_KEY: str = os.environ.get("GEMINI_PROXY_API_KEY", "")
GEMINI_PROXY_ENDPOINT: str = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://127.0.0.1:8045")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash-high")

# Per-task model overrides
STAGE1_MODEL: str = os.environ.get("STAGE1_MODEL", "gemini-3.1-pro-low")
STAGE2_DEDUP_MODEL: str = os.environ.get("STAGE2_DEDUP_MODEL", "gemini-3.1-flash-lite")
STAGE5_MODEL: str = os.environ.get("STAGE5_MODEL", "gemini-3.6-flash-low")
KB_INGEST_MODEL: str = os.environ.get("KB_INGEST_MODEL", "gemini-3.6-flash-medium")
SCORER_TEXT_MODEL: str = os.environ.get("SCORER_TEXT_MODEL", "gemini-3.6-flash-high")
SCORER_VISION_MODEL: str = os.environ.get("SCORER_VISION_MODEL", "gemini-3.1-pro")
VISION_MODEL: str = os.environ.get("VISION_MODEL", SCORER_VISION_MODEL)

OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3")

# ── Cognitive Continuity Harness ─────────────────────────────────────────────
LLM_MAX_REPAIR_ATTEMPTS: int = int(os.environ.get("LLM_MAX_REPAIR_ATTEMPTS", "2"))
LLM_DEGRADATION_RESET_THRESHOLD: int = int(os.environ.get("LLM_DEGRADATION_RESET_THRESHOLD", "3"))
LLM_ANCHOR_SCHEMA_IN_SYSTEM: bool = os.environ.get("LLM_ANCHOR_SCHEMA_IN_SYSTEM", "true").lower() == "true"

# ── Firecrawl / Crawler ──────────────────────────────────────────────────────
FIRECRAWL_ENDPOINT: str = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY: str = os.environ.get("FIRECRAWL_API_KEY", "")
CRAWLER_ENDPOINT: str = os.environ.get("CRAWLER_ENDPOINT", "http://crawler:8003")

# ── Search & Reputation APIs ─────────────────────────────────────────────────
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
SAFE_BROWSING_API_KEY: str = os.environ.get("SAFE_BROWSING_API_KEY", "")
URLHAUS_AUTH_KEY: str = os.environ.get("URLHAUS_AUTH_KEY", "")
HUNTER_API_KEY: str = os.environ.get("HUNTER_API_KEY", "")
APOLLO_API_KEY: str = os.environ.get("APOLLO_API_KEY", "")
SHODAN_API_KEY: str = os.environ.get("SHODAN_API_KEY", "")

# ── Tuning constants ──────────────────────────────────────────────────────────
MAX_ENRICHMENT_ATTEMPTS: int = int(os.environ.get("MAX_ENRICHMENT_ATTEMPTS", "3"))
ENRICHMENT_RETRY_HOURS: int = int(os.environ.get("ENRICHMENT_RETRY_HOURS", "24"))
KEYWORD_MIN_HITS: int = int(os.environ.get("KEYWORD_MIN_HITS", "5"))
STALE_REOPEN_DAYS: int = int(os.environ.get("STALE_REOPEN_DAYS", "90"))
SEARCH_COOLDOWN_DAYS: int = int(os.environ.get("SEARCH_COOLDOWN_DAYS", "30"))
FEW_SHOT_K: int = int(os.environ.get("FEW_SHOT_K", "5")) # Used 5 from evaluator
HUNTER_VERIFY_CONTACTS: bool = os.environ.get("HUNTER_VERIFY_CONTACTS", "true").lower() == "true"

# ── Cost-estimate pricing map (USD per unit) ──────────────────────────────────
PRICING_MAP = {
    "openrouter": {"input_per_token": 0.15 / 1_000_000, "output_per_token": 0.60 / 1_000_000},
    "gemini": {"input_per_token": 0.075 / 1_000_000, "output_per_token": 0.30 / 1_000_000},
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
    "apollo": {"per_query": 0.01},
    "shodan": {"per_query": 0.001},
}

logging.getLogger(__name__).info(
    "Common config loaded | SCORER_VISION_MODEL=%s | SCORER_TEXT_MODEL=%s | PROXY=%s",
    SCORER_VISION_MODEL, SCORER_TEXT_MODEL, GEMINI_PROXY_ENDPOINT,
)
