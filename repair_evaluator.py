import sys
sys.path.append('/app')
import psycopg2
import harness
import concurrent.futures

import traceback
import time

def process_candidate(cid):
    print(f"\n[EVALUATOR] =========================================")
    print(f"[EVALUATOR] Starting evaluation for candidate {cid}...")
    start_t = time.time()
    try:
        harness.score_candidate(cid)
        elapsed = time.time() - start_t
        print(f"[EVALUATOR] SUCCESS: Completed evaluation for {cid} in {elapsed:.2f}s.")
        
        # Verify in DB
        with psycopg2.connect("postgresql://leadscope:leadscope_dev@postgres:5432/leadscope") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT score, rationale FROM evaluations WHERE candidate_id = %s ORDER BY created_at DESC LIMIT 1", (cid,))
                res = cur.fetchone()
                if res:
                    print(f"[EVALUATOR] DB VERIFY {cid}: Score={res[0]}, Rationale length={len(str(res[1]))}")
                else:
                    print(f"[EVALUATOR] DB VERIFY {cid}: NO EVALUATION FOUND IN DB!")
        
        time.sleep(2)
    except Exception as e:
        elapsed = time.time() - start_t
        print(f"[EVALUATOR] FAILED to score candidate {cid} after {elapsed:.2f}s: {e}")
        traceback.print_exc()

def repair_evaluations():
    conn = psycopg2.connect("postgresql://leadscope:leadscope_dev@postgres:5432/leadscope")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT c.id 
        FROM candidates c
        LEFT JOIN LATERAL (
            SELECT score, rationale, evidence_data
            FROM evaluations
            WHERE candidate_id = c.id
            ORDER BY created_at DESC
            LIMIT 1
        ) e ON true
        WHERE c.status = 'pending_review' 
          AND c.campaign_id IN (1, 2)
          AND (e.score IS NULL OR e.rationale IS NULL OR jsonb_array_length(COALESCE(e.evidence_data->'images_analyzed', '[]'::jsonb)) = 0)
    """)
    
    candidate_ids = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    print(f"Found {len(candidate_ids)} candidates needing evaluation repair.")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        list(executor.map(process_candidate, candidate_ids))
        
    print("All evaluation repairs completed.")

if __name__ == "__main__":
    repair_evaluations()
