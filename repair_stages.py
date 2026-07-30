import sys
sys.path.append('/app')
import db
import stage5

def repair_enrichment():
    with db.get_conn() as conn:
        # Query candidates lacking complete enrichment data
        # We join campaigns to get the business_brief needed by _enrich_candidate
        approved = db.fetchall(
            conn,
            """
            SELECT c.id, c.campaign_id, c.domain, c.company_name, c.status,
                   c.enrichment_attempt_count, c.enrichment_attempted_at,
                   camp.id as camp_id, camp.business_brief, camp.slug, camp.settings,
                   l.id as existing_lead_id,
                   l.enrichment_report as existing_enrichment_report,
                   (
                       SELECT evidence_data
                       FROM evaluations
                       WHERE candidate_id = c.id
                       ORDER BY created_at DESC
                       LIMIT 1
                   ) as eval_evidence
            FROM candidates c
            JOIN campaigns camp ON camp.id = c.campaign_id
            LEFT JOIN leads l ON l.candidate_id = c.id
            WHERE c.status = 'pending_review' 
              AND c.campaign_id IN (1, 2)
              AND (
                  l.id IS NULL OR 
                  l.screenshot_url IS NULL OR 
                  (l.contact_email IS NULL AND l.contact_phone IS NULL) OR 
                  l.estimated_size IS NULL OR 
                  l.enrichment_report IS NULL
              )
            ORDER BY c.created_at ASC
            """
        )
        
    import time
    import traceback
    
    print(f"Found {len(approved)} candidates needing enrichment repair.")
    
    for i, candidate in enumerate(approved):
        cid = candidate['id']
        domain = candidate['domain']
        print(f"\n[STAGES] =========================================")
        print(f"[STAGES] [{i+1}/{len(approved)}] Enriching candidate {cid} ({domain})...")
        start_t = time.time()
        try:
            candidate["existing_enrichment_report"] = None
            candidate["existing_lead_id"] = None
            
            # CLEAR THE COOLDOWN in the DB before calling _enrich_candidate
            with db.get_conn() as inner_conn:
                db.execute(inner_conn, "UPDATE candidates SET enrichment_attempted_at = NULL, enrichment_attempt_count = 0 WHERE id = %s", (cid,))
                inner_conn.commit()
            
            with db.get_conn() as inner_conn:
                stage5._enrich_candidate(candidate, candidate, inner_conn, candidate.get("settings"))
            
            elapsed = time.time() - start_t
            print(f"[STAGES] SUCCESS: Enriched {domain} in {elapsed:.2f}s.")
            
            # Verify in DB
            with db.get_conn() as inner_conn:
                res = db.fetchone(inner_conn, "SELECT enrichment_report FROM leads WHERE candidate_id = %s", (cid,))
                if res and res['enrichment_report']:
                    print(f"[STAGES] DB VERIFY {cid}: Enrichment report length={len(str(res['enrichment_report']))}")
                else:
                    print(f"[STAGES] DB VERIFY {cid}: NO ENRICHMENT REPORT FOUND IN DB!")
                    
            time.sleep(2)
        except Exception as e:
            elapsed = time.time() - start_t
            print(f"[STAGES] FAILED to enrich {domain} after {elapsed:.2f}s: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    repair_enrichment()
