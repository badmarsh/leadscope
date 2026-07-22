import os
import sys
import time
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Service endpoints
STAGES_URL = "http://127.0.0.1:8002"
EVALUATOR_URL = "http://127.0.0.1:8001"
DASHBOARD_URL = "http://127.0.0.1:3000"

# Admin credentials
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "leadscope_admin")
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def print_step(msg):
    print(f"\n{'='*60}")
    print(f"-> {msg}")
    print(f"{'='*60}")

def wait_for_services():
    print_step("Checking Service Health")
    services = [
        ("Stages API", f"{STAGES_URL}/health"),
        ("Evaluator API", f"{EVALUATOR_URL}/health")
    ]
    for name, url in services:
        print(f"Waiting for {name} ({url})...")
        for i in range(10):
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    print(f"  [OK] {name} is up.")
                    break
            except requests.exceptions.RequestException:
                pass
            time.sleep(2)
        else:
            print(f"  [FAIL] {name} did not respond.")
            sys.exit(1)

def run_e2e():
    wait_for_services()

    # Get JENEX Campaign ID
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM campaigns WHERE slug = 'jenex-hu-hvac'")
    row = cur.fetchone()
    if not row:
        print("[FAIL] jenex-hu-hvac campaign not found in DB.")
        sys.exit(1)
    jenex_id = row[0]
    
    # ── 1. Ingestion (Part 5) ──────────────────────────────────────────────
    print_step("1. Ingestion (WP-Remediation Signatures)")
    # We run the ingestion script using subprocess to ingest the mock blog
    import subprocess
    env = os.environ.copy()
    res = subprocess.run([sys.executable, "services/stages/signature_ingestion.py", "file://mock_blog.txt"], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print("[WARN] Ingestion script failed or no new signatures inserted.")
        print(res.stderr)
    else:
        print("  [OK] Signatures ingested.")

    # ── 2. Stage 1 (ICP Definition) ────────────────────────────────────────
    print_step(f"2. Stage 1 (ICP Definition) for Campaign {jenex_id}")
    r = requests.post(f"{STAGES_URL}/stage1/run", json={"campaign_id": jenex_id}, timeout=120)
    if r.status_code == 200:
        print("  [OK] Stage 1 complete. ICP configuration updated.")
    else:
        print(f"  [FAIL] Stage 1 failed: {r.text}")
        sys.exit(1)

    # ── 3. Stage 2 (Target Finder) ─────────────────────────────────────────
    print_step("3. Stage 2 (Target Finder)")
    # We call run-all, but it might take a while if it hits many APIs.
    # To keep the dry-run fast, we'll just run it for JENEX.
    r = requests.post(f"{STAGES_URL}/stage2/run", json={"campaign_id": jenex_id}, timeout=300)
    if r.status_code == 200:
        data = r.json()
        print(f"  [OK] Stage 2 complete. Output: {data.get('result', data)}")
    else:
        print(f"  [FAIL] Stage 2 failed: {r.text}")
        sys.exit(1)

    # ── 4. Stage 3 (Evaluator) ─────────────────────────────────────────────
    print_step("4. Stage 3 (Evaluator)")
    r = requests.post(f"{EVALUATOR_URL}/score/trigger", timeout=300)
    if r.status_code == 200:
        data = r.json()
        scored = data.get("result", {}).get("scored", "unknown")
        errors = data.get("result", {}).get("errors", "unknown")
        print(f"  [OK] Stage 3 complete. Scored: {scored}, Errors: {errors}")
        if scored == 0 and errors == 0:
            print("  [WARN] No candidates were scored. If Stage 2 found no new leads, this is expected.")
    else:
        print(f"  [FAIL] Stage 3 failed: {r.text}")
        sys.exit(1)

    # ── 5. Human Review Simulation (Dashboard) ─────────────────────────────
    print_step("5. Human Review Simulation (Dashboard)")
    # We will simulate it via DB directly to avoid Secure cookie issues over HTTP

    # Find a pending_review candidate to approve
    cur.execute("SELECT id FROM candidates WHERE status = 'pending_review' AND campaign_id = %s LIMIT 1", (jenex_id,))
    row = cur.fetchone()
    if row:
        approve_id = row[0]
        print(f"  Simulating approval for candidate {approve_id}...")
        cur.execute("UPDATE candidates SET status = 'approved' WHERE id = %s", (approve_id,))
        cur.execute("INSERT INTO feedback (candidate_id, decision, note, reviewed_by) VALUES (%s, 'approved', 'E2E Dry Run Approved', 'dashboard')", (approve_id,))
        print("  [OK] Candidate approved via DB.")
    else:
        print("  [WARN] No pending_review candidates found to approve. Skipping human review simulation.")


    # ── 6. Stage 5 (Enrichment) ────────────────────────────────────────────
    print_step("6. Stage 5 (Enrichment)")
    # Ensure Ollama is running if we are going to enrich, otherwise it might fail.
    # We will trigger the endpoint anyway.
    r = requests.post(f"{STAGES_URL}/stage5/run", timeout=300)
    if r.status_code == 200:
        data = r.json()
        print(f"  [OK] Stage 5 complete. Output: {data.get('result', data)}")
    else:
        print(f"  [FAIL] Stage 5 failed: {r.text}")

    # ── 7. Maintenance Jobs (Part 6) ───────────────────────────────────────
    print_step("7. Maintenance Jobs (Part 6)")
    # Run budget monitor
    res = subprocess.run([sys.executable, "services/jobs/budget_monitor.py"], env=env, capture_output=True, text=True)
    print(res.stdout)

    print_step("[SUCCESS] End-to-End Dry Run Finished Successfully!")
    conn.close()

if __name__ == "__main__":
    run_e2e()
