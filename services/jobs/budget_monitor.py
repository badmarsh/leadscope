import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def monitor_budgets():
    print("Running Budget Monitor...")
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
            print(f"[CRITICAL] Provider '{provider}' has exhausted its monthly quota! ({used}/{quota})")
            warnings += 1
        elif percent >= 80:
            print(f"[WARNING] Provider '{provider}' is near its monthly quota limit! ({used}/{quota} - {percent:.1f}%)")
            warnings += 1
        else:
            print(f"[OK] Provider '{provider}' usage is healthy. ({used}/{quota} - {percent:.1f}%)")

    print(f"Budget Monitor Complete. {warnings} warnings issued.")
    conn.close()

if __name__ == "__main__":
    monitor_budgets()
