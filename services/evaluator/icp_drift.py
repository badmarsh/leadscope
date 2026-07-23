"""
icp_drift.py — Feature 6.10: Automatic ICP drift detection.

Detects if the human reviewer is consistently overriding the ICP configuration
(e.g., repeatedly rejecting leads that scored highly, or approving leads that scored low).
"""
import json
import logging
from typing import Any
import db
import llm

logger = logging.getLogger(__name__)

DRIFT_PROMPT = """
You are an expert sales operations analyst. 
We have an Ideal Customer Profile (ICP) used to score leads, but the human reviewer's recent feedback shows a pattern of overrides (e.g. rejecting high scores or approving low scores).

=== BEGIN SYSTEM INSTRUCTIONS ===
ICP Target Segments:
{target_segments}

ICP Disqualifiers:
{disqualifiers}

Your task is to analyze the feedback and identify IF there is a systemic "drift" in what the human actually wants vs what the ICP says.
If there is a drift, provide a concrete, actionable suggestion for how to update the ICP to align with the human's decisions.
If there is no clear pattern (just random noise), indicate no drift.

Return ONLY valid JSON with the following keys:
- "drift_detected": boolean
- "confidence": "high" | "medium" | "low"
- "analysis": 2-3 sentences explaining the pattern observed (if any).
- "suggested_icp_update": A concrete suggestion to update the ICP (e.g., "Add 'software development' to disqualifiers"). Empty if no drift.
=== END SYSTEM INSTRUCTIONS ===

=== BEGIN USER DATA ===
Recent Feedback from Human Reviewer:
{feedback_json}
=== END USER DATA ===
"""

def analyze_drift(campaign_id: int) -> dict[str, Any] | None:
    """
    Analyze recent feedback for a campaign to detect ICP drift.
    Returns the drift analysis dict, or None if not enough data.
    """
    try:
        with db.get_conn() as conn:
            # Check how many decisions have been made since last analysis
            camp = db.fetchone(
                conn,
                "SELECT icp_drift_decisions_at_analysis FROM campaigns WHERE id = %s",
                (campaign_id,)
            )
            if not camp:
                return None
                
            last_analysis_count = camp["icp_drift_decisions_at_analysis"] or 0
            
            # Count total feedback items
            count_res = db.fetchone(
                conn,
                "SELECT COUNT(*) as count FROM feedback WHERE campaign_id = %s",
                (campaign_id,)
            )
            total_feedback = count_res["count"] if count_res else 0
            
            # Only analyze if we have at least 10 new pieces of feedback since last analysis
            if total_feedback - last_analysis_count < 10:
                return None
                
            # Fetch recent feedback (last 50)
            feedbacks = db.fetchall(
                conn,
                """
                SELECT f.decision, f.note, e.score, e.rationale
                FROM feedback f
                JOIN evaluations e ON e.candidate_id = f.candidate_id
                WHERE f.campaign_id = %s
                ORDER BY f.created_at DESC
                LIMIT 50
                """,
                (campaign_id,)
            )
            
            if len(feedbacks) < 10:
                return None
                
            # Fetch current ICP
            icp_row = db.fetchone(
                conn,
                "SELECT icp_config FROM campaigns WHERE id = %s",
                (campaign_id,)
            )
            icp = json.loads(icp_row["icp_config"]) if icp_row and icp_row.get("icp_config") else {}

        # Prepare LLM prompt
        prompt = DRIFT_PROMPT.format(
            target_segments=json.dumps(icp.get("target_segments", []), indent=2),
            disqualifiers=json.dumps(icp.get("disqualifiers", {}), indent=2),
            feedback_json=json.dumps(feedbacks, indent=2)
        )
        
        result, _, _, _, _ = llm.chat_json(prompt, temperature=0.2)
        if "_raw" in result:
            logger.warning("ICP drift analysis failed: LLM returned non-JSON")
            return None
            
        # Update campaign with result
        with db.get_conn() as conn:
            db.execute(
                conn,
                """
                UPDATE campaigns 
                SET icp_drift_suggestion = %s,
                    icp_drift_analyzed_at = NOW(),
                    icp_drift_decisions_at_analysis = %s
                WHERE id = %s
                """,
                (json.dumps(result) if result.get("drift_detected") else None, total_feedback, campaign_id)
            )
                
        return result
    except Exception as exc:
        logger.error("ICP drift analysis failed for campaign %s: %s", campaign_id, exc)
        return None
