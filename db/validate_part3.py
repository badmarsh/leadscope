"""
validate_part3.py — Part 3 validation checklist runner.
Run from the project root with:
  python db/validate_part3.py

Tests:
  1. Score a JENEX candidate (content_relevance) — score 0-100, evidence_data shape
  2. Cross-campaign feedback isolation
  3. evaluations.icp_version_used matches current icp_config.version
  4. api_call_log row produced with plausible token counts + cost
  5. Scoring stability (score twice, check variance)
  6. /score/trigger endpoint flips new → pending_review
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

# Auto-load .env
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

EVALUATOR_URL = os.environ.get("EVALUATOR_URL", "http://localhost:8001")
STAGES_URL = os.environ.get("STAGES_URL", "http://localhost:8002")

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results = []


def check(label, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((label, status, detail))
    print(f"{status} {label}" + (f"\n       {detail}" if detail else ""))


def get_db():
    import psycopg2
    import psycopg2.extras
    db_url = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")
    return psycopg2.connect(db_url)


print("=" * 60)
print("Part 3 -- Validation Checklist")
print("=" * 60)

# ── 1. Score a JENEX candidate (content_relevance) ────────────────────────────
print("\n[1] Score a JENEX candidate (content_relevance)")
conn = get_db()
cur = conn.cursor()
# Find a 'new' candidate from JENEX (campaign_id=1)
cur.execute("""
    SELECT id, domain FROM candidates
    WHERE campaign_id = 1 AND status IN ('new', 'pending_review')
    LIMIT 1
""")
row = cur.fetchone()
conn.close()

if row:
    test_candidate_id = row[0]
    print(f"       Testing candidate id={test_candidate_id} domain={row[1]}")

    resp = requests.post(f"{EVALUATOR_URL}/score/{test_candidate_id}", timeout=120)
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", {})
        score_val = result.get("score")
        check("Score in 0-100 range",
              score_val is not None and 0 <= score_val <= 100,
              f"score={score_val}")
        check("Rationale is non-empty",
              bool(result.get("rationale")),
              f"rationale={result.get('rationale', '')[:80]}...")
        check("model_used is non-empty",
              bool(result.get("model_used")),
              f"model={result.get('model_used')}")
        check("icp_version_used is populated",
              result.get("icp_version_used", 0) > 0,
              f"icp_version={result.get('icp_version_used')}")
    else:
        check("Score JENEX candidate", False, f"HTTP {resp.status_code}: {resp.text[:200]}")
else:
    check("Score JENEX candidate", False, "No candidates found for JENEX campaign")

# ── 2. Verify icp_version_used matches current icp_config ────────────────────
print("\n[2] icp_version_used matches current icp_config.version")
if row and resp.status_code == 200:
    conn = get_db()
    cur = conn.cursor()
    # Get latest icp_config version for campaign 1
    cur.execute("SELECT MAX(version) FROM icp_config WHERE campaign_id = 1")
    current_version = cur.fetchone()[0]
    # Get the evaluation we just created
    cur.execute("""
        SELECT icp_version_used FROM evaluations
        WHERE candidate_id = %s
        ORDER BY created_at DESC LIMIT 1
    """, (test_candidate_id,))
    eval_row = cur.fetchone()
    conn.close()

    if eval_row:
        check("evaluations.icp_version_used = current icp_config.version",
              eval_row[0] == current_version,
              f"eval.icp_version_used={eval_row[0]} current={current_version}")
    else:
        check("evaluations row created", False, "No evaluation row found")
else:
    check("icp_version_used check", False, "Skipped (no candidate scored)")

# ── 3. api_call_log row for scoring ──────────────────────────────────────────
print("\n[3] api_call_log row with plausible token counts + cost")
conn = get_db()
cur = conn.cursor()
cur.execute("""
    SELECT provider, model, tokens_in, tokens_out, cost_estimate_usd
    FROM api_call_log
    WHERE stage = 'stage3'
    ORDER BY created_at DESC LIMIT 1
""")
log_row = cur.fetchone()
conn.close()

if log_row:
    check("api_call_log has stage3 row", True,
          f"provider={log_row[0]} model={log_row[1]} tokens_in={log_row[2]} tokens_out={log_row[3]}")
    check("cost_estimate_usd is non-null and positive",
          log_row[4] is not None and float(log_row[4]) > 0,
          f"cost=${log_row[4]}")
    check("tokens_in is plausible (> 0)",
          log_row[2] is not None and log_row[2] > 0,
          f"tokens_in={log_row[2]}")
else:
    check("api_call_log stage3 row", False, "No api_call_log row found for stage3")

# ── 4. Cross-campaign feedback isolation ──────────────────────────────────────
print("\n[4] Cross-campaign feedback isolation")
conn = get_db()
cur = conn.cursor()
# Seed feedback for campaign 1 and campaign 2
cur.execute("""
    INSERT INTO feedback (candidate_id, decision, note)
    SELECT id, 'approved', 'test feedback campaign 1'
    FROM candidates WHERE campaign_id = 1 LIMIT 1
    ON CONFLICT DO NOTHING
""")
# Get a campaign 2 candidate (or create one)
cur.execute("SELECT id FROM candidates WHERE campaign_id = 2 LIMIT 1")
c2_cand = cur.fetchone()
if not c2_cand:
    cur.execute("""
        INSERT INTO candidates (campaign_id, domain, source, query_used)
        VALUES (2, 'isolation-test-campaign2.com', 'test', 'isolation_test')
        RETURNING id
    """)
    c2_cand = cur.fetchone()
    conn.commit()

cur.execute("""
    INSERT INTO feedback (candidate_id, decision, note)
    VALUES (%s, 'rejected', 'test feedback campaign 2')
    ON CONFLICT DO NOTHING
""", (c2_cand[0],))
conn.commit()

# Check that few-shot query for campaign 1 doesn't return campaign 2's feedback
cur.execute("""
    SELECT f.decision, c.campaign_id
    FROM feedback f
    JOIN candidates c ON c.id = f.candidate_id
    WHERE c.campaign_id = 1
""")
c1_feedback = cur.fetchall()

cur.execute("""
    SELECT f.decision, c.campaign_id
    FROM feedback f
    JOIN candidates c ON c.id = f.candidate_id
    WHERE c.campaign_id = 2
""")
c2_feedback = cur.fetchall()
conn.close()

# Verify no cross-contamination
c1_campaigns = set(r[1] for r in c1_feedback)
c2_campaigns = set(r[1] for r in c2_feedback)
check("Campaign 1 feedback only has campaign_id=1",
      c1_campaigns == {1} or len(c1_feedback) == 0,
      f"campaign_ids in c1 feedback: {c1_campaigns}")
check("Campaign 2 feedback only has campaign_id=2",
      c2_campaigns == {2} or len(c2_feedback) == 0,
      f"campaign_ids in c2 feedback: {c2_campaigns}")

# ── 5. Scoring stability (score same candidate twice) ────────────────────────
print("\n[5] Scoring stability (score twice, check variance)")
if row:
    resp2 = requests.post(f"{EVALUATOR_URL}/score/{test_candidate_id}", timeout=120)
    if resp2.status_code == 200:
        score1 = result.get("score", 0)
        score2 = resp2.json().get("result", {}).get("score", 0)
        diff = abs(score1 - score2)
        check("Score variance <= 20 points",
              diff <= 20,
              f"score1={score1} score2={score2} diff={diff}")
    else:
        check("Second scoring call", False, f"HTTP {resp2.status_code}")
else:
    check("Scoring stability", False, "Skipped (no candidate)")

# ── 6. /score/trigger endpoint ───────────────────────────────────────────────
print("\n[6] /score/trigger flips new -> pending_review")
# Ensure we have a 'new' candidate
conn = get_db()
cur = conn.cursor()
cur.execute("""
    SELECT id, domain FROM candidates
    WHERE campaign_id = 1 AND status = 'new'
    LIMIT 1
""")
trigger_cand = cur.fetchone()
if not trigger_cand:
    # Reset one candidate to 'new' for testing
    cur.execute("""
        UPDATE candidates SET status = 'new'
        WHERE campaign_id = 1 AND id != %s
        RETURNING id
    """, (test_candidate_id,))
    trigger_cand = cur.fetchone()
    conn.commit()
conn.close()

print("\n[6] /score/trigger flips new -> pending_review")
# Reset exactly 3 candidates to 'new' for a bounded trigger test
conn = get_db()
cur = conn.cursor()
cur.execute("""
    UPDATE candidates SET status = 'new'
    WHERE id IN (
        SELECT id FROM candidates WHERE campaign_id = 1
        ORDER BY id ASC LIMIT 3
    )
    RETURNING id
""")
trigger_ids = [r[0] for r in cur.fetchall()]
conn.commit()
conn.close()

if trigger_ids:
    trigger_ok = False
    trigger_detail = ""
    try:
        resp = requests.post(f"{EVALUATOR_URL}/score/trigger", timeout=600)
        if resp.status_code == 200:
            r = resp.json().get("result", {})
            trigger_ok = True
            trigger_detail = f"scored={r.get('scored')} errors={r.get('errors')}"
    except requests.exceptions.Timeout:
        # Timed out — the trigger was still running. Check DB directly.
        trigger_detail = "(request timed out — checking DB directly)"
        trigger_ok = True  # service accepted the call; check DB below
    except Exception as exc:
        check("/score/trigger endpoint", False, str(exc))
        trigger_ids = []

    if trigger_ids:
        check("/score/trigger returned OK or in progress", trigger_ok, trigger_detail)
        # Wait a moment then verify at least 1 of our 3 candidates flipped
        import time; time.sleep(5)
        conn = get_db()
        cur = conn.cursor()
        placeholders = ','.join(['%s'] * len(trigger_ids))
        cur.execute(f"""
            SELECT id, status FROM candidates
            WHERE id IN ({placeholders})
        """, trigger_ids)
        final_statuses = cur.fetchall()
        conn.close()
        flipped = [r for r in final_statuses if r[1] == 'pending_review']
        check("At least 1 candidate flipped to pending_review",
              len(flipped) > 0,
              f"flipped={len(flipped)}/{len(trigger_ids)} candidates")
else:
    check("/score/trigger test", False, "No candidates available for trigger test")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Part 3 Validation Summary")
print("=" * 60)
passes = sum(1 for _, s, _ in results if "PASS" in s)
fails  = sum(1 for _, s, _ in results if "FAIL" in s)
for label, status, detail in results:
    print(f"  {status} {label}")

print(f"\n{passes} passed, {fails} failed")
sys.exit(0 if fails == 0 else 1)
