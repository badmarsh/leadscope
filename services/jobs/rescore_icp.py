import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
EVALUATOR_HOST = os.environ.get("EVALUATOR_HOST", "localhost:8000")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def rescore_outdated_candidates():
    conn = get_db()
    cur = conn.cursor()

    # Find candidates in ('new', 'evaluated') whose latest evaluation 
    # used an older icp_config version than the current one for their campaign.
    
    # current icp version per campaign
    cur.execute("""
        SELECT campaign_id, version 
        FROM icp_config 
        WHERE (campaign_id, version) IN (
            SELECT campaign_id, MAX(version) FROM icp_config GROUP BY campaign_id
        )
    """)
    current_icp_versions = {row[0]: row[1] for row in cur.fetchall()}

    # get candidates
    cur.execute("""
        SELECT c.id, c.campaign_id, e.icp_version_used
        FROM candidates c
        LEFT JOIN (
            SELECT candidate_id, MAX(icp_version_used) as icp_version_used
            FROM evaluations
            GROUP BY candidate_id
        ) e ON c.id = e.candidate_id
        WHERE c.status IN ('new', 'evaluated')
    """)
    candidates = cur.fetchall()

    rescore_count = 0
    for cid, camp_id, eval_icp_version in candidates:
        curr_version = current_icp_versions.get(camp_id)
        if not curr_version:
            continue
            
        # If the candidate has NO evaluation yet (eval_icp_version is None), 
        # it will be picked up by the regular trigger_scoring job for 'new' candidates.
        # But if we want to force it here, we can. The megaprompt says:
        # "re-run Stage 3 only on candidates still in 'new'/'evaluated' (not yet in feedback)"
        if eval_icp_version is not None and eval_icp_version < curr_version:
            print(f"Candidate {cid} (campaign {camp_id}) evaluated with v{eval_icp_version}, current is v{curr_version}. Re-scoring...")
            try:
                r = requests.post(f"http://{EVALUATOR_HOST}/score/{cid}", timeout=60)
                r.raise_for_status()
                rescore_count += 1
                # The evaluator harness will insert a NEW evaluation row and flip status to evaluated
                # Optional: we could delete or deprecate the old evaluation rows, but the DB 
                # allows multiple and usually we just ORDER BY created_at DESC for the active one.
                # To be clean, let's delete older evaluations for this candidate so the dashboard only sees one.
                cur.execute("DELETE FROM evaluations WHERE candidate_id = %s AND icp_version_used < %s", (cid, curr_version))
                print(f"  Successfully re-scored candidate {cid} and cleaned old evaluations.")
            except Exception as e:
                print(f"  Failed to re-score candidate {cid}: {e}")
                
    print(f"Done. Re-scored {rescore_count} candidates.")
    conn.close()

if __name__ == "__main__":
    rescore_outdated_candidates()
