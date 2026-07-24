import harness
import db

with db.get_conn() as conn:
    cands = db.fetchall(conn, "SELECT c.id, c.campaign_id, c.domain FROM candidates c JOIN campaigns camp ON c.campaign_id = camp.id WHERE c.status = 'new' AND camp.status = 'active' LIMIT 50")
    print("Found candidates:", cands)

res = harness.trigger_scoring()
print("Trigger result:", res)
