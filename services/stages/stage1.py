"""
stage1.py — Stage 1: Brief / ICP Definer.

Takes a campaign's business_brief + reference_materials, calls the LLM proxy
(OpenAI-compatible) to produce a structured ICP (target_segments, keywords_hu,
keywords_en, disqualifiers), inserts a new versioned icp_config row, and logs
the LLM call to api_call_log.

Gate: refuses to run if campaigns.status = 'draft'.
"""
import json
import logging
from typing import Any

import services.common.config as config
import db
import cost_log
import services.common.llm as llm

logger = logging.getLogger(__name__)

STAGE1_SYSTEM = (
    "You are an expert B2B market analyst helping define an Ideal Customer Profile (ICP) "
    "for a lead-generation campaign. Return ONLY valid JSON matching the schema below. "
    "No markdown, no prose outside the JSON."
)

STAGE1_PROMPT = """
Business brief:
{brief}

Reference materials:
{reference_materials}

Produce a structured ICP in JSON format with exactly these top-level keys:
- "target_segments": array of objects, each with:
    - "name": segment name (string)
    - "description": one sentence description (string)
    - "priority": "high" | "medium" | "low"
- "keywords_hu": array of Hungarian-language search query strings that would
  find businesses matching this ICP on Google/Exa/Tavily.
  Include location modifiers (e.g. "Magyarország", city names).
  Aim for 8-15 queries.
- "keywords_en": array of English-language search query strings for the same purpose.
  Include "Hungary" or "Hungarian" as location modifiers where relevant.
  Aim for 5-10 queries.
- "disqualifiers": object with:
    - "exclude_if": array of strings — characteristics that disqualify a business
    - "sectors_out": array of strings — sector/type exclusions

Return ONLY the JSON object. No markdown fences.
"""


def run(campaign_id: int) -> dict[str, Any]:
    """
    Run Stage 1 for the given campaign_id.
    Returns a summary dict. Raises ValueError if campaign is draft or not found.
    Fix C2/H4: entire logic runs inside a single `with db.get_conn() as conn:` block
    so the connection is not returned to the pool prematurely.
    """
    if not db.acquire_stage_lock(campaign_id, "stage1"):
        logger.info("Stage 1 is already running for campaign %s", campaign_id)
        return {"status": "skipped", "reason": "already running"}
    try:
        with db.get_conn() as conn:
            # ── 1. Load campaign ──────────────────────────────────────────────────
            campaign = db.fetchone(
                conn,
                "SELECT id, slug, name, status, business_brief, reference_materials FROM campaigns WHERE id = %s",
                (campaign_id,),
            )
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")

            if campaign["status"] == "draft":
                raise ValueError(
                    f"Campaign '{campaign['slug']}' is status='draft'. "
                    "Business brief not yet filled in for this campaign — see §0.3"
                )

            # ── 2. Determine next version number ──────────────────────────────────
            latest = db.fetchone(
                conn,
                "SELECT MAX(version) AS v FROM icp_config WHERE campaign_id = %s",
                (campaign_id,),
            )
            next_version = (latest["v"] or 0) + 1

            # ── 3. Build prompt ───────────────────────────────────────────────────
            ref_str = json.dumps(campaign["reference_materials"] or {}, ensure_ascii=False)
            prompt = STAGE1_PROMPT.format(
                brief=campaign["business_brief"],
                reference_materials=ref_str,
            )

            # ── 4. Call LLM via OpenAI-compatible proxy (§0.4 pattern) ─────────────
            logger.info("Stage 1: calling LLM (%s) for campaign %s v%s", config.STAGE1_MODEL, campaign_id, next_version)
            icp, tokens_in, tokens_out, _, _ = llm.chat_json(
                prompt,
                system_prompt=STAGE1_SYSTEM,
                temperature=0.2,
                model=config.STAGE1_MODEL,
            )

            # ── 5. Log the LLM call ───────────────────────────────────────────────
            cost_log.log_call(
                conn,
                stage="stage1",
                provider="gemini",
                campaign_id=campaign_id,
                model=config.STAGE1_MODEL,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

            # ── 6. Validate the JSON structure ────────────────────────────────────
            if "_raw" in icp:
                raise ValueError(f"LLM returned non-JSON: {icp['_raw'][:300]}")

            required_keys = {"target_segments", "keywords_hu", "keywords_en", "disqualifiers"}
            missing = required_keys - icp.keys()
            if missing:
                raise ValueError(f"LLM omitted required keys: {missing}")

            if not isinstance(icp.get("keywords_hu"), list) or not icp["keywords_hu"]:
                raise ValueError("keywords_hu must be a non-empty list")
            if not isinstance(icp.get("keywords_en"), list) or not icp["keywords_en"]:
                raise ValueError("keywords_en must be a non-empty list")
            if not isinstance(icp.get("disqualifiers"), list):
                icp["disqualifiers"] = []

            # ── 7. Insert icp_config row ──────────────────────────────────────────
            row = db.execute_returning(
                conn,
                """
                INSERT INTO icp_config
                    (campaign_id, version, target_segments, keywords_hu, keywords_en, disqualifiers)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, version
                """,
                (
                    campaign_id,
                    next_version,
                    json.dumps(icp["target_segments"]),
                    icp["keywords_hu"],
                    icp["keywords_en"],
                    json.dumps(icp["disqualifiers"]),
                ),
            )

            logger.info(
                "Stage 1 complete: campaign=%s icp_config.id=%s version=%s "
                "segments=%d keywords_hu=%d keywords_en=%d",
                campaign_id,
                row["id"],
                row["version"],
                len(icp["target_segments"]),
                len(icp["keywords_hu"]),
                len(icp["keywords_en"]),
            )

            result = {
                "campaign_id": campaign_id,
                "icp_config_id": row["id"],
                "version": row["version"],
                "segments": len(icp["target_segments"]),
                "keywords_hu": icp["keywords_hu"],
                "keywords_en": icp["keywords_en"],
                "disqualifiers": icp["disqualifiers"],
            }

        db.set_stage_status(campaign_id, "stage1", "idle")
        return result
    except Exception:
        db.set_stage_status(campaign_id, "stage1", "failed")
        raise
