import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("budget_monitor")

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def monitor_budgets():
    logger.info("Running Budget Monitor...")
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT pb.provider, pb.monthly_quota, COALESCE(SUM(acl.query_count), 0) as used
        FROM provider_budgets pb
        LEFT JOIN api_call_log acl 
          ON pb.provider = acl.provider 
          AND date_trunc('month', acl.created_at) = date_trunc('month', now())
        GROUP BY pb.provider, pb.monthly_quota
    """)
    budgets = cur.fetchall()

    warnings = 0
    for provider, quota, used in budgets:
        if quota is None or quota == 0:
            continue
            
        percent = (used / quota) * 100
        
        if percent >= 100:
            logger.critical("Provider '%s' has exhausted its monthly quota! (%s/%s)", provider, used, quota)
            warnings += 1
        elif percent >= 80:
            logger.warning("Provider '%s' is near its monthly quota limit! (%s/%s - %.1f%%)", provider, used, quota, percent)
            warnings += 1
        else:
            logger.info("Provider '%s' usage is healthy. (%s/%s - %.1f%%)", provider, used, quota, percent)

    cur.execute("""
        SELECT campaign_id, provider, SUM(query_count) as used, SUM(estimated_cost) as total_cost
        FROM api_call_log
        WHERE date_trunc('month', created_at) = date_trunc('month', now())
        GROUP BY campaign_id, provider
        ORDER BY campaign_id, provider
    """)
    campaign_usage = cur.fetchall()
    
    logger.info("--- Campaign Monthly Breakdown ---")
    for cmp_id, prov, cmp_used, total_cost in campaign_usage:
        logger.info("Campaign %s - Provider '%s': %s queries (Est. Cost: $%.4f)", cmp_id, prov, cmp_used, total_cost or 0.0)
    logger.info("----------------------------------")

    logger.info("Budget Monitor Complete. %d warnings issued.", warnings)
    conn.close()

if __name__ == "__main__":
    monitor_budgets()
