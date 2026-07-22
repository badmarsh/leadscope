"""
validate_part6.py — Part 6 validation checklist (Maintenance Jobs).
"""
import os
import sys
import json
import subprocess
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []

def check(label, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((label, status, detail))
    print(f"{status} {label}" + (f"\n       {detail}" if detail else ""))

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

print("=" * 60)
print("Part 6 -- Validation Checklist (Maintenance Jobs)")
print("=" * 60)

conn = get_db()
cur = conn.cursor()

# Get campaign IDs
cur.execute("SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
wp_campaign_id = cur.fetchone()[0]

cur.execute("SELECT id FROM campaigns WHERE slug = 'jenex-hu-hvac'")
jenex_campaign_id = cur.fetchone()[0]

env = os.environ.copy()
env["DATABASE_URL"] = DATABASE_URL
env["PYTHONIOENCODING"] = "utf-8"

# ── 1. Re-verification (6.1) ───────────────────────────────────────────────
print("\n[6.1] Testing Re-verification job...")
# Insert a candidate with a missing signature
cur.execute("DELETE FROM candidates WHERE domain = 'file://mock_blog.txt' AND campaign_id = %s", (wp_campaign_id,))
evidence = json.dumps({"signatures": ["this_code_does_not_exist_in_mock_blog"]})
cur.execute("""
    INSERT INTO candidates (campaign_id, domain, status, evidence_data)
    VALUES (%s, 'file://mock_blog.txt', 'approved', %s)
    RETURNING id
""", (wp_campaign_id, evidence))
cand_id = cur.fetchone()[0]

res = subprocess.run([sys.executable, "services/jobs/reverify_wp.py"], env=env, capture_output=True, text=True)
print(res.stdout)
check("Re-verify job runs without error", res.returncode == 0)

cur.execute("SELECT status FROM candidates WHERE id = %s", (cand_id,))
status = cur.fetchone()[0]
check("Candidate missing signature flipped to 'stale'", status == "stale", f"status={status}")

# ── 2. Re-scoring (6.2) ────────────────────────────────────────────────────
print("\n[6.2] Testing Re-scoring job...")
# Insert a test candidate and evaluation with an old ICP version
cur.execute("DELETE FROM evaluations WHERE candidate_id IN (SELECT id FROM candidates WHERE domain = 'rescore-test.com')")
cur.execute("DELETE FROM candidates WHERE domain = 'rescore-test.com' AND campaign_id = %s", (jenex_campaign_id,))
cur.execute("""
    INSERT INTO candidates (campaign_id, domain, company_name, status, source)
    VALUES (%s, 'rescore-test.com', 'Rescore Test', 'pending_review', 'manual')
    RETURNING id
""", (jenex_campaign_id,))
rescore_cand_id = cur.fetchone()[0]

# Give it an evaluation with icp_version_used = 0 (outdated)
cur.execute("""
    INSERT INTO evaluations (candidate_id, score, rationale, icp_version_used)
    VALUES (%s, 50, 'Old eval', 0)
""", (rescore_cand_id,))

# Ensure the campaign has an icp_config with version > 0
cur.execute("SELECT MAX(version) FROM icp_config WHERE campaign_id = %s", (jenex_campaign_id,))
max_icp = cur.fetchone()[0] or 1

env["EVALUATOR_HOST"] = "127.0.0.1:8001"

print("Using docker evaluator on port 8001 for test...")

res = subprocess.run([sys.executable, "services/jobs/rescore_icp.py"], env=env, capture_output=True, text=True)
print(res.stdout)

check("Re-score job runs without error", res.returncode == 0)

cur.execute("SELECT icp_version_used, score FROM evaluations WHERE candidate_id = %s ORDER BY created_at DESC LIMIT 1", (rescore_cand_id,))
row = cur.fetchone()
check("Candidate was re-scored with current ICP version", row is not None and row[0] == max_icp, f"icp_version_used={row[0] if row else None}")

# ── 3. Golden Regression (6.3) ─────────────────────────────────────────────
print("\n[6.3] Testing Golden Regression Suite...")
res = subprocess.run([sys.executable, "services/jobs/golden_regression.py"], env=env, capture_output=True, text=True)
print(res.stdout)
check("Golden Regression Suite passes", res.returncode == 0, f"rc={res.returncode}")

# ── 4. Budget Monitor (6.4) ────────────────────────────────────────────────
print("\n[6.4] Testing Budget Monitor...")
cur.execute("""
    INSERT INTO provider_budgets (provider, monthly_quota) 
    VALUES ('testprovider', 10) 
    ON CONFLICT (provider) DO UPDATE SET monthly_quota = 10
""")
cur.execute("DELETE FROM api_call_log WHERE provider = 'testprovider'")
# Insert 10 usage
cur.execute("""
    INSERT INTO api_call_log (stage, provider, query_count)
    VALUES ('test', 'testprovider', 10)
""")

res = subprocess.run([sys.executable, "services/jobs/budget_monitor.py"], env=env, capture_output=True, text=True)
print(res.stdout)
check("Budget monitor runs without error", res.returncode == 0)
check("Budget monitor prints CRITICAL for exhausted budget", "[CRITICAL] Provider 'testprovider' has exhausted" in res.stdout)

# cleanup test provider
cur.execute("DELETE FROM api_call_log WHERE provider = 'testprovider'")
cur.execute("DELETE FROM provider_budgets WHERE provider = 'testprovider'")
conn.close()

print("\n" + "=" * 60)
print("Part 6 Validation Summary")
print("=" * 60)
passes = sum(1 for _, s, _ in results if "PASS" in s)
fails  = sum(1 for _, s, _ in results if "FAIL" in s)
for label, status, detail in results:
    print(f"  {status} {label}")

print(f"\n{passes} passed, {fails} failed")
sys.exit(0 if fails == 0 else 1)
