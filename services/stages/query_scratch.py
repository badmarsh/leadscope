import db

def test_query():
    with db.get_conn() as conn:
        approved = db.fetchall(
            conn,
            """
            SELECT c.id, c.campaign_id, c.domain, c.company_name, c.status,
                   c.enrichment_attempt_count, c.enrichment_attempted_at,
                   camp.business_brief, camp.slug, camp.settings,
                   (
                       SELECT id
                       FROM leads
                       WHERE candidate_id = c.id
                       LIMIT 1
                   ) as existing_lead_id,
                   (
                       SELECT evidence_data
                       FROM evaluations
                       WHERE candidate_id = c.id
                       ORDER BY created_at DESC
                       LIMIT 1
                   ) as eval_evidence
            FROM candidates c
            JOIN campaigns camp ON camp.id = c.campaign_id
            WHERE c.status IN ('pending_review', 'approved')
            ORDER BY c.created_at ASC
            """
        )
        print("Total fetched:", len(approved))

if __name__ == "__main__":
    test_query()
