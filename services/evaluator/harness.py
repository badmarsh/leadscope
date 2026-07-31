"""
harness.py — Shared evaluator harness.

Orchestrates: load candidate → load campaign → load icp_config →
fetch few-shot feedback → dispatch to scorer → write evaluations + api_call_log.
"""
import json
import logging
import time
import concurrent.futures
from typing import Any

import services.common.config as config
import db
import icp_drift
from scorers import content_relevance, image_quality, threat_intel
from scorers import performance_gap, gdpr_gap, accessibility_risk
from services.common import cost_gate

logger = logging.getLogger(__name__)

def _recover_stuck_evaluations(conn):
    """
    On service startup or run start, reset status for candidates that were
    claimed but never finished due to a crash.
    """
    count = db.execute(
        conn,
        """
        UPDATE candidates
        SET status = 'new'
        WHERE status = 'evaluating'
          AND campaign_id IN (
              SELECT id FROM campaigns WHERE stage3_status != 'running'
          )
        """
    )
    if count > 0:
        logger.warning("Stage 3 crash recovery: reset %d stuck evaluations to 'new'.", count)

# ── Scorer registry keyed by campaigns.evaluator_type ──────────────────────────
# NOTE (v3 judgment call from spec): three hardcoded strategies, not a DB-driven
# prompt system. The dict itself is the extension point if a fourth ever shows up.
def _threat_intel_fast(candidate, campaign, icp, few_shot):
    candidate = dict(candidate)
    candidate["_campaign_settings"] = {
        **(candidate.get("_campaign_settings") or {}),
        "skip_phase_x": True
    }
    return threat_intel.score(candidate, campaign, icp, few_shot)

SCORER_REGISTRY = {
    "content_relevance": content_relevance.score,
    "image_quality": image_quality.score,
    "threat_intel": threat_intel.score,
    "threat_intel_fast": _threat_intel_fast,
    "auto": content_relevance.score,
    # Campaign 8: Core Web Vitals Red-Zone Detector (no LLM, pure PSI API)
    "performance_gap": performance_gap.score,
    # Campaign 9: GDPR/Cookie Consent Compliance Gap (no LLM, Playwright network intercept)
    "gdpr_gap": gdpr_gap.score,
    # Campaign 1: ADA/WCAG Accessibility Violation Detector (no LLM, axe-core)
    "accessibility_risk": accessibility_risk.score,
}


def _status_from_score(score: int, min_score: int = 20, is_shitty: bool = False) -> str:
    if is_shitty or score < min_score:
        return "discarded"
    else:
        return "approved"


def _select_scorer(campaign: dict):
    eval_type = campaign.get("evaluator_type")
    if eval_type in SCORER_REGISTRY:
        return SCORER_REGISTRY[eval_type]
    logger.warning("Unrecognized or missing evaluator_type %r for campaign %s. Defaulting to content_relevance.", eval_type, campaign.get("id"))
    return SCORER_REGISTRY["content_relevance"]


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
    Retrieve the k most recent feedback decisions for this campaign.
    Includes both approved and rejected decisions to provide balanced context to the LLM.
    Few-shot pools must never cross campaigns (spec requirement).
    """
    if k is None:
        k = config.FEW_SHOT_K

    rows = db.fetchall(
        conn,
        """
        SELECT f.decision, f.note, c.domain, c.company_name
        FROM feedback f
        JOIN candidates c ON c.id = f.candidate_id
        WHERE c.campaign_id = %s
        ORDER BY f.created_at DESC
        LIMIT %s
        """,
        (campaign_id, k),
    )
    return rows


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

        evaluator_type = campaign.get("evaluator_type", "content_relevance")
        scorer_fn = _select_scorer(campaign)
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
            db.update_candidate_generation(conn, candidate_id, candidate.get("processing_generation", 0), {"status": "discarded"})
            return {"candidate_id": candidate_id, "score": 0, "rationale": "Domain is on Do Not Contact list."}

        # Check for duplicates using safe interval arithmetic
        dup = db.fetchone(
            conn,
            """
            SELECT id FROM candidates
            WHERE domain = %s AND campaign_id = %s AND id != %s
              AND created_at > NOW() - (%s * INTERVAL '1 day')
            ORDER BY created_at DESC LIMIT 1
            """,
            (candidate["domain"], candidate["campaign_id"], candidate_id, config.STALE_REOPEN_DAYS)
        )
        if dup:
            db.update_candidate_generation(conn, candidate_id, candidate.get("processing_generation", 0), {"status": "duplicate", "duplicate_of_candidate_id": int(dup["id"])})
            return {"candidate_id": candidate_id, "score": 0, "rationale": f"Duplicate of candidate {dup['id']} within {config.STALE_REOPEN_DAYS} days."}

        # 3. Load current ICP version
        icp, icp_version = _load_icp(conn, campaign["id"])

        # 4. Retrieve few-shot feedback (same campaign only)
        few_shot = _load_few_shot(conn, campaign["id"])

        # Check budget before LLM dispatch
        if not cost_gate.check_budget(conn, campaign["id"], "stage3"):
            logger.warning("Budget ceiling reached for campaign %s - skipping candidate %s", campaign["id"], candidate_id)
            db.update_candidate_generation(conn, candidate_id, candidate.get("processing_generation", 0), {"status": "new"})
            return {"candidate_id": candidate_id, "score": 0, "rationale": "Budget ceiling reached."}

        # 5. Dispatch to the matching scorer
        settings = json.loads(campaign.get("settings") or "{}") if isinstance(campaign.get("settings"), str) else (campaign.get("settings") or {})
        candidate["_campaign_settings"] = settings
        logger.info(
            "Scoring candidate %s (domain=%s) with %s scorer (icp v%s, %d few-shot)",
            candidate_id, candidate["domain"], evaluator_type, icp_version, len(few_shot),
        )
        result = scorer_fn(candidate, campaign, icp, few_shot)

        # URLScan fast-track: only apply bonus when snippet is confirmed, and
        # make the bonus amount campaign-configurable (default 20, was hardcoded 40)
        if candidate.get("source") == "urlscan":
            original_score = result.get("score", 0)
            settings = json.loads(campaign.get("settings") or "{}") if isinstance(campaign.get("settings"), str) else (campaign.get("settings") or {})
            bonus = int(settings.get("urlscan_score_bonus", 20))
            snippet_confirmed = result.get("evidence_data", {}).get("snippet_confirmed", False)
            if snippet_confirmed:
                result["score"] = min(100, original_score + bonus)
                result["rationale"] = f"(URLScan Confirmed +{bonus}) " + result.get("rationale", "")
            else:
                # URLScan source but snippet not confirmed — no bonus, keep raw score
                result["rationale"] = "(URLScan Unconfirmed — no bonus applied) " + result.get("rationale", "")

        if result.get("_raw") or (isinstance(result.get("evidence_data"), dict) and result["evidence_data"].get("raw_response")):
            attempts = (candidate.get("evidence_data") or {}).get("eval_attempts", 0) + 1
            if attempts >= 3:
                logger.error(
                    "Cognitive failure for candidate %s (domain=%s): max retries (%d) exceeded.",
                    candidate_id, candidate["domain"], attempts,
                )
                ev_data = candidate.get("evidence_data") or {}
                ev_data["eval_attempts"] = attempts
                db.update_candidate_generation(conn, candidate_id, candidate.get("processing_generation", 0), {"status": "discarded", "evidence_data": json.dumps(ev_data)})
                return {"candidate_id": candidate_id, "score": 0, "rationale": f"LLM cognitive failure {attempts} times — discarded."}
            else:
                logger.error(
                    "Cognitive failure for candidate %s (domain=%s) (attempt %d/3). "
                    "Resetting status to 'new' for retry on next run.",
                    candidate_id, candidate["domain"], attempts,
                )
                ev_data = candidate.get("evidence_data") or {}
                ev_data["eval_attempts"] = attempts
                db.update_candidate_generation(conn, candidate_id, candidate.get("processing_generation", 0), {"status": "new", "evidence_data": json.dumps(ev_data)})
                return {"candidate_id": candidate_id, "score": 0, "rationale": f"LLM cognitive failure (attempt {attempts}) — will retry."}

        # 6. Write to evaluations
        # Optimistic concurrency check: if user clicked "Rerun Evaluation", status was reset to 'new'
        curr = db.fetchone(conn, "SELECT status FROM candidates WHERE id = %s", (candidate_id,))
        if not curr or curr["status"] != 'evaluating':
            logger.info("Candidate %s was reset during scoring. Aborting save.", candidate_id)
            return {"candidate_id": candidate_id, "score": 0, "aborted": True}

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
                result.get("rationale", ""),
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
            "rationale": result.get("rationale", ""),
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
        _recover_stuck_evaluations(conn)

    with db.get_conn() as conn:
        if campaign_id:
            camp = db.fetchone(conn, "SELECT settings FROM campaigns WHERE id = %s", (campaign_id,))
            settings = json.loads(camp["settings"]) if camp and isinstance(camp.get("settings"), str) else (camp.get("settings") or {})
            limit = int(settings.get("evaluator_batch_size", 50))
            new_candidates = db.claim_candidates_for_stage(
                conn,
                campaign_id=campaign_id,
                from_statuses=["new"],
                to_status="evaluating",
                limit=limit,
                order_by_source=True
            )
        else:
            # NOTE: Global fetch without specific campaign_id is tricky with our new claim helper.
            # We will just fetch active campaigns and pick the first one, or do a global claim.
            # For simplicity, if campaign_id is None, let's fetch active campaign_ids and claim for each.
            active_camps = db.fetchall(conn, "SELECT id FROM campaigns WHERE status = 'active'")
            new_candidates = []
            for camp in active_camps:
                cands = db.claim_candidates_for_stage(
                    conn,
                    campaign_id=camp["id"],
                    from_statuses=["new"],
                    to_status="evaluating",
                    limit=50,
                    order_by_source=True
                )
                new_candidates.extend(cands)
                if len(new_candidates) >= 50:
                    break

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
                
                if result.get("aborted"):
                    return {"candidate_id": cand["id"], "status": "aborted"}

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
                        db.update_candidate_generation(conn, cand["id"], cand.get("processing_generation", 0), {"status": "discarded"})
                        logger.info("Auto-rejected candidate %s: %s", cand["id"], reject_note)
                    else:
                        db.update_candidate_generation(conn, cand["id"], cand.get("processing_generation", 0), {"status": "evaluated"})
                        logger.info("Candidate %s passed evaluation (score %s >= %s) and is evaluated", cand["id"], score, min_score)
                return {"candidate_id": cand["id"], "status": "scored", "score": score}
            except Exception as exc:
                logger.error("Harness failed for candidate %s: %s", cand["id"], exc)
                return {"candidate_id": cand["id"], "status": "error", "error": str(exc)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            for res in executor.map(process_cand, new_candidates):
                if res is None:
                    break
                results.append(res)
                if res["status"] == "scored":
                    scored += 1
                else:
                    errors += 1

        # Backpressure: slow down polling when backlog is large
        batch_size = len(new_candidates)
        if batch_size >= 100:
            time.sleep(5)   # Heavy backlog — throttle to protect token budget
        elif batch_size >= 20:
            time.sleep(2)
        else:
            time.sleep(0.5)

        # ICP drift detection: run after every batch to catch evaluation pattern shifts
        for cid in locked_campaign_ids:
            try:
                drift_result = icp_drift.analyze_drift(cid)
                if drift_result and drift_result.get("drift_detected"):
                    logger.warning(
                        "ICP DRIFT DETECTED for campaign %s (confidence: %s): %s",
                        cid,
                        drift_result.get("confidence", "unknown"),
                        drift_result.get("suggested_icp_update", "see icp_drift_suggestion column"),
                    )
            except Exception as drift_exc:
                logger.debug("ICP drift check skipped for campaign %s: %s", cid, drift_exc)

        return {
            "scored": scored,
            "errors": errors,
            "details": results
        }
    finally:
        for cid in locked_campaign_ids:
            db.set_stage_status(cid, "stage3", "idle")
