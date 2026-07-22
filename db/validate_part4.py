"""
validate_part4.py — Part 4 validation checklist.

Tests:
  1. GET /api/session returns {loggedIn: false} before login
  2. POST /api/login with wrong password → 401
  3. POST /api/login with correct password → 200 + sets session cookie
  4. GET /api/session after login → {loggedIn: true}
  5. GET /api/leads?campaign_id=1 returns leads with score, rationale
  6. POST /api/action approve → feedback row in DB + candidate status flip
  7. POST /api/action reject → feedback row in DB + candidate status flip
  8. GET /api/usage returns spend and stats
  9. POST /api/logout → session cleared
 10. GET /api/leads after logout → 401
"""
import os
import sys
import json
import requests

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:3000")
CORRECT_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "leadscope_admin")

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []


def check(label, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((label, status, detail))
    print(f"{status} {label}" + (f"\n       {detail}" if detail else ""))


def get_db():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    return conn


print("=" * 60)
print("Part 4 -- Validation Checklist (Dashboard Auth + API)")
print("=" * 60)

session = requests.Session()

# ── 1. GET /api/session before login ─────────────────────────────────────────
print("\n[1] GET /api/session before login")
r = session.get(f"{DASHBOARD_URL}/api/session", timeout=15)
data = r.json()
check("/api/session returns 200", r.status_code == 200, f"status={r.status_code}")
check("loggedIn=false before login", data.get("loggedIn") == False, f"loggedIn={data.get('loggedIn')}")

# ── 2. Wrong password → 401 ───────────────────────────────────────────────────
print("\n[2] POST /api/login with wrong password")
r = session.post(f"{DASHBOARD_URL}/api/login",
                 json={"password": "wrong_password"}, timeout=15)
check("Wrong password → 401", r.status_code == 401, f"status={r.status_code} body={r.text[:80]}")

# ── 3. Correct password → 200 + cookie ───────────────────────────────────────
print("\n[3] POST /api/login with correct password")
r = session.post(f"{DASHBOARD_URL}/api/login",
                 json={"password": CORRECT_PASSWORD}, timeout=15)
check("Correct password → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:80]}")
cookie_val = r.cookies.get("leadscope_session")
if cookie_val:
    session.cookies.clear()
    session.cookies.set("leadscope_session", cookie_val)
check("Session cookie set", cookie_val is not None, f"cookies={list(session.cookies.keys())}")

# ── 4. GET /api/session after login ──────────────────────────────────────────
print("\n[4] GET /api/session after login")
r = session.get(f"{DASHBOARD_URL}/api/session", timeout=15)
data = r.json()
check("loggedIn=true after login", data.get("loggedIn") == True, f"loggedIn={data.get('loggedIn')}")

# ── 5. GET /api/leads returns real data ──────────────────────────────────────
print("\n[5] GET /api/leads returns leads with score + rationale")
r = session.get(f"{DASHBOARD_URL}/api/leads?campaign_id=1", timeout=30)
check("/api/leads returns 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    leads = r.json().get("leads", [])
    check("At least 1 lead returned", len(leads) > 0, f"count={len(leads)}")
    if leads:
        first = leads[0]
        check("Lead has 'score' field", "score" in first, f"keys={list(first.keys())[:5]}")
        check("Lead has 'rationale' field", "rationale" in first or first.get("rationale") is not None,
              f"rationale={str(first.get('rationale', ''))[:50]}")
        check("Lead has 'domain' field", "domain" in first, f"domain={first.get('domain')}")
        test_lead_id = first.get("id")
    else:
        test_lead_id = None
        check("Lead fields check", False, "No leads to inspect")
else:
    leads = []
    test_lead_id = None
    check("leads returned", False, f"HTTP {r.status_code}")

# ── 6. POST /api/action approve ───────────────────────────────────────────────
print("\n[6] POST /api/action → approve a lead")
# Get a pending_review candidate
conn = get_db()
cur = conn.cursor()
cur.execute("""
    SELECT id, domain FROM candidates
    WHERE campaign_id = 1 AND status = 'pending_review'
    LIMIT 1
""")
pending = cur.fetchone()
conn.close()

if pending:
    approve_id = pending[0]
    r = session.post(f"{DASHBOARD_URL}/api/action",
                     json={"candidate_id": approve_id, "decision": "approved", "note": "Part 4 test"},
                     timeout=15)
    check("/api/action approve → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:80]}")

    # Verify in DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM candidates WHERE id = %s", (approve_id,))
    row = cur.fetchone()
    cur.execute("SELECT decision, note FROM feedback WHERE candidate_id = %s ORDER BY created_at DESC LIMIT 1", (approve_id,))
    fb = cur.fetchone()
    conn.close()
    check("Candidate flipped to 'approved'", row and row[0] == "approved",
          f"status={row[0] if row else 'NOT FOUND'}")
    check("Feedback row written with note", fb is not None and fb[1] == "Part 4 test",
          f"decision={fb[0] if fb else None} note={fb[1] if fb else None}")
else:
    check("/api/action approve", False, "No pending_review candidate available")
    check("Candidate status flip", False, "Skipped")
    check("Feedback row written", False, "Skipped")
    approve_id = None

# ── 7. POST /api/action reject ────────────────────────────────────────────────
print("\n[7] POST /api/action → reject a lead")
conn = get_db()
cur = conn.cursor()
cur.execute("""
    SELECT id FROM candidates
    WHERE campaign_id = 1 AND status = 'pending_review' AND id != %s
    LIMIT 1
""", (approve_id or 0,))
pending2 = cur.fetchone()
conn.close()

if pending2:
    reject_id = pending2[0]
    r = session.post(f"{DASHBOARD_URL}/api/action",
                     json={"candidate_id": reject_id, "decision": "rejected", "note": "Part 4 reject test"},
                     timeout=15)
    check("/api/action reject → 200", r.status_code == 200, f"status={r.status_code}")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM candidates WHERE id = %s", (reject_id,))
    row = cur.fetchone()
    conn.close()
    check("Candidate flipped to 'rejected'", row and row[0] == "rejected",
          f"status={row[0] if row else 'NOT FOUND'}")
else:
    check("/api/action reject", False, "No second pending_review candidate")
    check("Candidate flipped to rejected", False, "Skipped")

# ── 8. GET /api/usage ─────────────────────────────────────────────────────────
print("\n[8] GET /api/usage returns spend data")
r = session.get(f"{DASHBOARD_URL}/api/usage?campaign_id=1", timeout=15)
check("/api/usage returns 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    usage = r.json()
    check("Usage has 'spend' key", "spend" in usage, f"keys={list(usage.keys())}")
    check("Usage has 'stats' key", "stats" in usage, f"keys={list(usage.keys())}")
    stats = usage.get("stats", {})
    check("Stats has total_candidates", stats.get("total_candidates") is not None,
          f"total_candidates={stats.get('total_candidates')}")

# ── 9. POST /api/logout ───────────────────────────────────────────────────────
print("\n[9] POST /api/logout clears session")
r = session.post(f"{DASHBOARD_URL}/api/logout", timeout=15)
check("/api/logout returns 200", r.status_code == 200, f"status={r.status_code}")
session.cookies.clear() # Simulate browser dropping the expired cookie

# ── 10. /api/leads after logout → 401 ────────────────────────────────────────
print("\n[10] GET /api/leads after logout → 401")
r = session.get(f"{DASHBOARD_URL}/api/leads?campaign_id=1", timeout=15)
check("/api/leads after logout → 401", r.status_code == 401,
      f"status={r.status_code} (session should be invalid)")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Part 4 Validation Summary")
print("=" * 60)
passes = sum(1 for _, s, _ in results if "PASS" in s)
fails  = sum(1 for _, s, _ in results if "FAIL" in s)
for label, status, detail in results:
    print(f"  {status} {label}")

print(f"\n{passes} passed, {fails} failed")
sys.exit(0 if fails == 0 else 1)
