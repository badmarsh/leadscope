"""
harness.py — Shared evaluator harness.

Orchestrates: load candidate → load campaign → load icp_config →
fetch few-shot feedback → dispatch to scorer → write evaluations + api_call_log.
"""
import json
import logging
import concurrent.futures
from typing import Any

import config
import db
from scorers import content_relevance, image_quality, threat_intel

logger = logging.getLogger(__name__)

# ── Scorer registry keyed by campaigns.evaluator_type ──────────────────────────
# NOTE (v3 judgment call from spec): three hardcoded strategies, not a DB-driven
# prompt system. The dict itself is the extension point if a fourth ever shows up.
SCORER_REGISTRY = {
    "content_relevance": content_relevance.score,
    "image_quality": image_quality.score,
    "threat_intel": threat_intel.score,
}


def _status_from_score(score: int, min_score: int = 20, is_shitty: bool = False) -> str:
    if is_shitty or score < min_score:
        return "discarded"
    else:
        return "approved"


def _select_scorer(campaign: dict):
    if campaign.get("campaign_type") == "wp_remediation":  # HARDENING: removed magic id==3
        return SCORER_REGISTRY["threat_intel"]
    eval_type = campaign.get("evaluator_type")
    if not eval_type:
        ctype = campaign.get("campaign_type", "")
        if "shoe" in ctype or "photo" in ctype:
            eval_type = "image_quality"
        else:
            eval_type = "content_relevance"
    return SCORER_REGISTRY.get(eval_type, SCORER_REGISTRY["content_relevance"])


def _load_icp(conn, campaign_id: int) -> tuple[dict, int]:
    """
    Load the current (latest version) icp_config for a campaign.
    Returns (icp_dict, version_number).
    """
    row = db.fetchone(
        conn,
        """
        SELECT version, target_segments, keywords_hu, keywords_en, disqualifiers
        FROM icp_config
        WHERE campaign_id = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (campaign_id,),
    )
    if not row:
        return {}, 0

    # Parse JSON fields if they're strings
    icp = {
        "target_segments": json.loads(row["target_segments"]) if isinstance(row["target_segments"], str) else row["target_segments"],
        "keywords_hu": row["keywords_hu"] or [],
        "keywords_en": row["keywords_en"] or [],
        "disqualifiers": json.loads(row["disqualifiers"]) if isinstance(row["disqualifiers"], str) else row["disqualifiers"],
    }
    return icp, row["version"]


def _load_few_shot(conn, campaign_id: int, k: int = None) -> list[dict]:
    """
    Retrieve the k most recent feedback decisions for this campaign,
    balanced 50/50 between approved and rejected to prevent LLM score drift.
    Few-shot pools must never cross campaigns (spec requirement).
    """
    if k is None:
        k = config.FEW_SHOT_K

    half = max(1, k // 2)

    approved_rows = db.fetchall(
        conn,
        """
        SELECT f.decision, f.note, c.domain, c.company_name
        FROM feedback f
        JOIN candidates c ON c.id = f.candidate_id
        WHERE c.campaign_id = %s AND f.decision = 'approved'
        ORDER BY f.created_at DESC
        LIMIT %s
        """,
        (campaign_id, half),
    )
    rejected_rows = db.fetchall(
        conn,
        """
        SELECT f.decision, f.note, c.domain, c.company_name
        FROM feedback f
        JOIN candidates c ON c.id = f.candidate_id
        WHERE c.campaign_id = %s AND f.decision = 'rejected'
        ORDER BY f.created_at DESC
        LIMIT %s
        """,
        (campaign_id, half),
    )
    # Interleave: approved[0], rejected[0], approved[1], rejected[1]...
    combined = []
    for pair in zip(approved_rows, rejected_rows):
        combined.extend(pair)
    # Append any leftovers if one pool is smaller than the other
    combined.extend(approved_rows[len(rejected_rows):])
    combined.extend(rejected_rows[len(approved_rows):])
    return combined[:k]


def _log_call(conn, campaign_id: int, provider: str, model: str, tokens_in: int, tokens_out: int) -> None:
    """Write a row to api_call_log for this scoring call."""
    pricing = config.PRICING_MAP.get(provider, {})
    if "input_per_token" in pricing:
        cost = round(
            tokens_in * pricing["input_per_token"] + tokens_out * pricing["output_per_token"],
            6,
        )
    else:
        cost = 0.0

    db.execute(
        conn,
        """
        INSERT INTO api_call_log
            (campaign_id, stage, provider, model, tokens_in, tokens_out, query_count, cost_estimate_usd)
        VALUES (%s, 'stage3', %s, %s, %s, %s, 1, %s)
        """,
        (campaign_id, provider, model, tokens_in or None, tokens_out or None, cost),
    )


def score_candidate(candidate_id: int) -> dict[str, Any]:
    """
    Score a single candidate through the full harness pipeline.
    Returns the evaluation result dict.
    Raises ValueError if candidate/campaign not found or evaluator_type unknown.
    """
    with db.get_conn() as conn:
        # 1. Load candidate
        candidate = db.fetchone(
            conn,
            """
            SELECT id, campaign_id, domain, company_name, source,
                   query_used, evidence_data, status
            FROM candidates WHERE id = %s
            """,
            (candidate_id,),
        )
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        # 2. Load campaign config
        campaign = db.fetchone(
            conn,
            """
            SELECT id, slug, name, evaluator_type, business_brief
            FROM campaigns WHERE id = %s
            """,
            (candidate["campaign_id"],),
        )
        if not campaign:
            raise ValueError(f"Campaign {candidate['campaign_id']} not found")

        evaluator_type = campaign["evaluator_type"]
        scorer_fn = SCORER_REGISTRY.get(evaluator_type)
        if not scorer_fn:
            raise ValueError(f"Unknown evaluator_type: {evaluator_type!r}")

        # Check DNC list
        is_dnc = db.fetchone(
            conn,
            """
            SELECT 1 FROM do_not_contact
            WHERE (LOWER(%s) = LOWER(domain) OR %s LIKE '%%.' || domain)
              AND (campaign_id = %s OR campaign_id IS NULL)
            LIMIT 1
            """,
            (candidate["domain"], candidate["domain"], candidate["campaign_id"]),
        )
        if is_dnc:
            db.execute(conn, "UPDATE candidates SET status = 'discarded' WHERE id = %s", (candidate_id,))
            return {"candidate_id": candidate_id, "score": 0, "rationale": "Domain is on Do Not Contact list."}

        # Check for duplicates using safe interval arithmetic
        dup = db.fetchone(
            conn,
            """
            SELECT id FROM candidates
            WHERE domain = %s AND campaign_id = %s AND id != %s
              AND created_at > NOW() - (30 * INTERVAL '1 day')
            ORDER BY created_at DESC LIMIT 1
            """,
            (candidate["domain"], candidate["campaign_id"], candidate_id)
        )
        if dup:
            import json
            dup_id_json = json.dumps(int(dup["id"]))
            db.execute(
                conn, 
                "UPDATE candidates SET status = 'duplicate', duplicate_of_candidate_id = %s WHERE id = %s",
                (dup_id_json, candidate_id)
            )
            return {"candidate_id": candidate_id, "score": 0, "rationale": f"Duplicate of candidate {dup['id']} within 30 days."}

        # 3. Load current ICP version
        icp, icp_version = _load_icp(conn, campaign["id"])

        # 4. Retrieve few-shot feedback (same campaign only)
        few_shot = _load_few_shot(conn, campaign["id"])

        # 5. Dispatch to the matching scorer
        logger.info(
            "Scoring candidate %s (domain=%s) with %s scorer (icp v%s, %d few-shot)",
            candidate_id, candidate["domain"], evaluator_type, icp_version, len(few_shot),
        )
        result = scorer_fn(candidate, campaign, icp, few_shot)

        if result.get("_raw") or (isinstance(result.get("evidence_data"), dict) and result["evidence_data"].get("raw_response")):
            logger.error(
                "Cognitive failure for candidate %s (domain=%s): LLM returned _raw after all retries. "
                "Resetting status to 'new' for retry on next run.",
                candidate_id, candidate["domain"],
            )
            db.execute(
                conn,
                "UPDATE candidates SET status = 'new' WHERE id = %s",
                (candidate_id,),
            )
            return {"candidate_id": candidate_id, "score": 0, "rationale": "LLM cognitive failure — will retry."}

        # 6. Write to evaluations
        eval_row = db.execute_returning(
            conn,
            """
            INSERT INTO evaluations
                (candidate_id, score, rationale, evidence_urls, evidence_data,
                 model_used, icp_version_used, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'approved')
            RETURNING id, score, icp_version_used
            """,
            (
                candidate_id,
                result["score"],
                result["rationale"],
                result.get("evidence_urls", []),
                json.dumps(result.get("evidence_data", {})),
                result.get("model_used", ""),
                icp_version,
            ),
        )

        # 7. Log the API call
        _log_call(
            conn,
            campaign_id=campaign["id"],
            provider=result.get("provider", "openrouter"),
            model=result.get("model_used", ""),
            tokens_in=result.get("tokens_in", 0),
            tokens_out=result.get("tokens_out", 0),
        )

        logger.info(
            "Evaluation complete: candidate=%s score=%s eval_id=%s icp_v=%s",
            candidate_id, result["score"], eval_row["id"], icp_version,
        )

        return {
            "candidate_id": candidate_id,
            "evaluation_id": eval_row["id"],
            "score": result["score"],
            "rationale": result["rationale"],
            "evidence_data": result.get("evidence_data", {}),
            "icp_version_used": icp_version,
            "model_used": result.get("model_used", ""),
            "provider": result.get("provider", ""),
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
        }


def trigger_scoring(campaign_id: int | None = None) -> dict:
    """
    Poll for candidates with status='new', score each, flip to 'pending_review'.
    This is the bridge between Stage 2 (produces 'new') and the dashboard
    (displays 'pending_review').
    """
    with db.get_conn() as conn:
        if campaign_id:
            camp = db.fetchone(conn, "SELECT settings FROM campaigns WHERE id = %s", (campaign_id,))
            settings = json.loads(camp["settings"]) if camp and isinstance(camp.get("settings"), str) else (camp.get("settings") or {})
            limit = int(settings.get("evaluator_batch_size", 50))
            new_candidates = db.fetchall(
                conn,
                """
                SELECT id, campaign_id, domain, company_name
                FROM candidates
                WHERE status = 'new' AND campaign_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (campaign_id, limit)
            )
        else:
            new_candidates = db.fetchall(
                conn,
                """
                SELECT id, campaign_id, domain, company_name
                FROM candidates
                WHERE status = 'new'
                ORDER BY created_at ASC
                LIMIT 50
                """
            )

    campaign_ids = {c["campaign_id"] for c in new_candidates}
    
    # Pre-fetch settings for all involved campaigns to avoid scope issues
    campaign_settings = {}
    
    # We must filter out campaigns we couldn't acquire lock for, so we don't process their candidates
    locked_campaign_ids = set()
    for cid in campaign_ids:
        if not db.acquire_stage_lock(cid, "stage3"):
            logger.info("Stage 3 already running for campaign %s", cid)
            continue
        locked_campaign_ids.add(cid)
        with db.get_conn() as conn:
            camp = db.fetchone(conn, "SELECT settings FROM campaigns WHERE id = %s", (cid,))
            if camp:
                cs = json.loads(camp["settings"]) if isinstance(camp.get("settings"), str) else (camp.get("settings") or {})
                campaign_settings[cid] = cs
            else:
                campaign_settings[cid] = {}
                
    # Filter candidates to only those belonging to locked campaigns
    new_candidates = [cand for cand in new_candidates if cand["campaign_id"] in locked_campaign_ids]

    try:
        results = []
        scored = 0
        errors = 0

        def process_cand(cand):
            cid = cand["campaign_id"]
            if db.check_stop_signal(cid, "stage3"):
                logger.info("Stage 3 stopped via dashboard signal for campaign %s", cid)
                return None
                
            try:
                result = score_candidate(cand["id"])

                domain = (cand.get("domain") or "").lower()
                company_name = (cand.get("company_name") or "").lower()
                score = result.get("score", 0)

                # Auto-reject shitty entries
                is_shitty = False
                reject_note = ""
                cand_settings = campaign_settings.get(cid, {})
                min_score = int(cand_settings.get("min_score_for_review", 20))
                
                evidence = result.get("evidence_data", {})
                rationale_lower = result.get("rationale", "").lower()

                blocked_terms = cand_settings.get("blocked_domain_terms", [])
                if isinstance(blocked_terms, str):
                    blocked_terms = [t.strip().lower() for t in blocked_terms.split(",") if t.strip()]
                elif isinstance(blocked_terms, list):
                    blocked_terms = [str(t).lower() for t in blocked_terms]

                if any(t in domain for t in blocked_terms) or any(t in company_name for t in blocked_terms):
                    is_shitty = True
                    reject_note = f"Auto-rejected: Matches blocked term from campaign settings."
                elif score < min_score:
                    is_shitty = True
                    reject_note = f"Auto-rejected: Ultra irrelevant or no data retrieved (score {score} < {min_score})."
                elif evidence.get("photo_quality") == "professional":
                    is_shitty = True
                    reject_note = "Auto-rejected: Already uses professional photography (ultra irrelevant)."
                elif evidence.get("product_type") == "other":
                    is_shitty = True
                    reject_note = "Auto-rejected: Product type identified as non-shoe business."
                elif any(kw in rationale_lower for kw in ["veľká značka", "global brand", "major brand", "big brand"]):
                    is_shitty = True
                    reject_note = "Auto-rejected: Identified as a major/global brand (ultra irrelevant)."

                with db.get_conn() as conn:
                    if is_shitty:
                        db.execute(
                            conn,
                            "UPDATE candidates SET status = 'discarded' WHERE id = %s",
                            (cand["id"],)
                        )
                        logger.info("Auto-rejected candidate %s: %s", cand["id"], reject_note)
                    else:
                        db.execute(
                            conn,
                            "UPDATE candidates SET status = 'pending_review' WHERE id = %s",
                            (cand["id"],)
                        )
                        logger.info("Candidate %s passed evaluation (score %s >= %s) and is pending review", cand["id"], score, min_score)
                return {"candidate_id": cand["id"], "status": "scored", "score": score}
            except Exception as exc:
                logger.error("Harness failed for candidate %s: %s", cand["id"], exc)
                return {"candidate_id": cand["id"], "status": "error", "error": str(exc)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            for res in executor.map(process_cand, new_candidates):
                if res is None:
                    break
                results.append(res)
                if res["status"] == "scored":
                    scored += 1
                else:
                    errors += 1

        return {
            "scored": scored,
            "errors": errors,
            "details": results
        }
    finally:
        for cid in campaign_ids:
            db.set_stage_status(cid, "stage3", "idle")
