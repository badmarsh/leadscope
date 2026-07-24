"""
config.py — Centralised env-var loading for the evaluator service.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]

# ── LLM providers ────────────────────────────────────────────────────────────
# Primary: OpenRouter for evaluator scoring (Part 3 spec)
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL: str = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

# Fallback: local Gemini proxy (OpenAI-compat format)
GEMINI_PROXY_API_KEY: str = os.environ.get("GEMINI_PROXY_API_KEY", "")
GEMINI_PROXY_ENDPOINT: str = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://127.0.0.1:8045")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash-high")

# Per-task model overrides — set in .env to tune cost/quality per call site
# Evaluator scorers (stage 3 — runs every 15 min)
SCORER_TEXT_MODEL: str = os.environ.get("SCORER_TEXT_MODEL", "gemini-3.6-flash-high")   # content_relevance + threat_intel
SCORER_VISION_MODEL: str = os.environ.get("SCORER_VISION_MODEL", "gemini-3.1-pro") # image_quality
STAGE5_MODEL: str = os.environ.get("STAGE5_MODEL", "gemini-3.6-flash-low")

# Vision model for image_quality scorer (legacy alias kept for backwards compat)
VISION_MODEL: str = os.environ.get("VISION_MODEL", SCORER_VISION_MODEL)

# ── Cognitive Continuity Harness ─────────────────────────────────────────────
LLM_MAX_REPAIR_ATTEMPTS: int = int(os.environ.get("LLM_MAX_REPAIR_ATTEMPTS", "2"))
LLM_DEGRADATION_RESET_THRESHOLD: int = int(os.environ.get("LLM_DEGRADATION_RESET_THRESHOLD", "3"))
LLM_ANCHOR_SCHEMA_IN_SYSTEM: bool = os.environ.get("LLM_ANCHOR_SCHEMA_IN_SYSTEM", "true").lower() == "true"

# ── Firecrawl (still used by content_relevance + image_quality scorers) ────────
FIRECRAWL_ENDPOINT: str = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY: str = os.environ.get("FIRECRAWL_API_KEY", "")

# ── Self-hosted Crawl4AI (used by threat_intel scorer for JS-rendered re-verification) ──
CRAWLER_ENDPOINT: str = os.environ.get("CRAWLER_ENDPOINT", "http://crawler:8003")

# ── Reputation APIs (optional secondary corroboration for threat_intel) ────────
SAFE_BROWSING_API_KEY: str = os.environ.get("SAFE_BROWSING_API_KEY", "")
VIRUSTOTAL_API_KEY: str = os.environ.get("VIRUSTOTAL_API_KEY", "")
URLHAUS_AUTH_KEY: str = os.environ.get("URLHAUS_AUTH_KEY", "")

# ── Few-shot ──────────────────────────────────────────────────────────────────
# Max number of past feedback decisions to include as few-shot examples
FEW_SHOT_K: int = int(os.environ.get("FEW_SHOT_K", "5"))

# ── Cost-estimate pricing map (USD per unit) ──────────────────────────────────
PRICING_MAP = {
    "openrouter": {"input_per_token": 0.15 / 1_000_000, "output_per_token": 0.60 / 1_000_000},
    "gemini": {"input_per_token": 0.075 / 1_000_000, "output_per_token": 0.30 / 1_000_000},
    "firecrawl": {"per_query": 0.0},   # self-hosted (content_relevance + image_quality)
    "crawler": {"per_query": 0.0},     # self-hosted Crawl4AI (threat_intel)
}

import logging as _logging
_logging.getLogger(__name__).info(
    "Evaluator config loaded | SCORER_VISION_MODEL=%s | SCORER_TEXT_MODEL=%s | PROXY=%s",
    SCORER_VISION_MODEL, SCORER_TEXT_MODEL, GEMINI_PROXY_ENDPOINT,
)
