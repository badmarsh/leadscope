"""
watchdog.py — Stage health watchdog.

Alerts via Slack webhook (or logs a critical warning) if any campaign stage
has been in 'running' status for more than WATCHDOG_TIMEOUT_MINUTES.
Called from the main FastAPI startup and periodically from the scheduler.
"""
import logging
import os
import requests

import db

logger = logging.getLogger(__name__)

WATCHDOG_TIMEOUT_MINUTES = int(os.environ.get("WATCHDOG_TIMEOUT_MINUTES", "30"))
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def check_stuck_stages():
    """
    Find campaigns with stages stuck in 'running' for longer than WATCHDOG_TIMEOUT_MINUTES.
    Logs a CRITICAL warning and optionally sends a Slack alert.
    """
    try:
        with db.get_conn() as conn:
            stuck = db.fetchall(
                conn,
                """
                SELECT id, slug, stage1_status, stage2_status, stage3_status, stage5_status,
                       stage5_last_run
                FROM campaigns
                WHERE 'running' IN (stage1_status, stage2_status, stage3_status, stage5_status)
                  AND COALESCE(stage5_last_run, now() - interval '1 hour') < now() - make_interval(mins => %s)
                """,
                (WATCHDOG_TIMEOUT_MINUTES,),
            )

        if not stuck:
            return

        for campaign in stuck:
            msg = (
                f"⚠️ STUCK STAGE DETECTED: Campaign `{campaign['slug']}` (id={campaign['id']}) "
                f"has had a stage running for >{WATCHDOG_TIMEOUT_MINUTES}min. "
                f"Statuses: stage1={campaign['stage1_status']} stage2={campaign['stage2_status']} "
                f"stage3={campaign['stage3_status']} stage5={campaign['stage5_status']}"
            )
            logger.critical(msg)

            if SLACK_WEBHOOK_URL:
                try:
                    requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=5)
                except Exception as exc:
                    logger.warning("Failed to send Slack alert: %s", exc)

    except Exception as exc:
        logger.error("Watchdog check failed: %s", exc)
