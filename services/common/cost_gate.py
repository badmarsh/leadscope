"""
cost_gate.py - T1.4: Daily LLM budget ceiling.

Call check_budget(conn, campaign_id, stage) before every LLM invocation.
Returns False and logs CRITICAL when daily spend exceeds the limit.
"""
import logging
import db

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT_USD = 50.0


def check_budget(conn, campaign_id: int, stage: str, daily_limit_usd: float = DEFAULT_DAILY_LIMIT_USD) -> bool:
    """
    Returns True if spending is within budget, False if the daily limit is exceeded.
    Logs a CRITICAL warning when the limit is breached so it shows up in monitoring.
    """
    try:
        row = db.fetchone(
            conn,
            """
            SELECT COALESCE(SUM(cost_estimate_usd), 0) AS today_spend
            FROM api_call_log
            WHERE campaign_id = %s
              AND stage = %s
              AND created_at > now() - INTERVAL '1 day'
            """,
            (campaign_id, stage),
        )
        today_spend = float((row or {}).get("today_spend") or 0)
        if today_spend >= daily_limit_usd:
            logger.critical(
                "BUDGET CEILING REACHED: campaign=%s stage=%s spent=USD %.4f (limit=USD %.2f). LLM call suppressed.",
                campaign_id, stage, today_spend, daily_limit_usd,
            )
            return False
        return True
    except Exception as exc:
        # Fail open: if we cannot check the budget, allow the call and log the error
        logger.warning("Budget check failed for campaign=%s stage=%s: %s (failing open)", campaign_id, stage, exc)
        return True
