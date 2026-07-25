import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluator.icp_drift import analyze_drift
import stages.db as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("icp_drift_job")

def run():
    logger.info("Running ICP Drift Monitor...")
    with db.get_conn() as conn:
        campaigns = db.fetchall(conn, "SELECT id FROM campaigns")
        
    for c in campaigns:
        campaign_id = c["id"]
        res = analyze_drift(campaign_id)
        if res:
            logger.info(f"Analyzed drift for campaign {campaign_id}: {res}")
        else:
            logger.info(f"No drift analysis for campaign {campaign_id} (not enough data or no drift).")

if __name__ == "__main__":
    run()
