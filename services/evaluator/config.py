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
SCORER_VISION_MODEL: str = os.environ.get("SCORER_VISION_MODEL", "gemini-3.1-flash-image") # image_quality

# Vision model for image_quality scorer (legacy alias kept for backwards compat)
VISION_MODEL: str = os.environ.get("VISION_MODEL", SCORER_VISION_MODEL)

# ── Firecrawl ────────────────────────────────────────────────────────────────
FIRECRAWL_ENDPOINT: str = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY: str = os.environ.get("FIRECRAWL_API_KEY", "")

# ── Few-shot ──────────────────────────────────────────────────────────────────
# Max number of past feedback decisions to include as few-shot examples
FEW_SHOT_K: int = int(os.environ.get("FEW_SHOT_K", "5"))

# ── Cost-estimate pricing map (USD per unit) ──────────────────────────────────
PRICING_MAP = {
    "openrouter": {"input_per_token": 0.15 / 1_000_000, "output_per_token": 0.60 / 1_000_000},
    "gemini": {"input_per_token": 0.075 / 1_000_000, "output_per_token": 0.30 / 1_000_000},
    "firecrawl": {"per_query": 0.0},   # self-hosted
}
