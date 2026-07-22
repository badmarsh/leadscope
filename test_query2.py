import db
with db.get_conn() as conn:
    approved = db.fetchall(conn, "SELECT c.id FROM candidates c WHERE c.status IN ('pending_review', 'approved')")
    print('Length:', len(approved))
