import psycopg2
import json

def generate_report():
    conn = psycopg2.connect("postgresql://leadscope:leadscope_dev@postgres:5432/leadscope")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            c.campaign_id,
            count(c.id) as total,
            count(c.id) FILTER (WHERE e.score IS NOT NULL) as has_score,
            count(c.id) FILTER (WHERE e.rationale IS NOT NULL) as has_rationale,
            count(c.id) FILTER (WHERE jsonb_array_length(COALESCE(e.evidence_data->'images_analyzed', '[]'::jsonb)) > 0) as has_images,
            count(c.id) FILTER (WHERE l.id IS NOT NULL) as has_lead_record,
            count(c.id) FILTER (WHERE l.screenshot_url IS NOT NULL) as has_screenshot,
            count(c.id) FILTER (WHERE l.contact_email IS NOT NULL OR l.contact_phone IS NOT NULL) as has_contact,
            count(c.id) FILTER (WHERE l.estimated_size IS NOT NULL) as has_size,
            count(c.id) FILTER (WHERE l.enrichment_report IS NOT NULL) as has_brief
        FROM candidates c
        LEFT JOIN LATERAL (
            SELECT score, rationale, evidence_data
            FROM evaluations
            WHERE candidate_id = c.id
            ORDER BY created_at DESC
            LIMIT 1
        ) e ON true
        LEFT JOIN leads l ON l.candidate_id = c.id
        WHERE c.status = 'pending_review' AND c.campaign_id IN (1, 2)
        GROUP BY c.campaign_id
        ORDER BY c.campaign_id;
    """)
    
    results = cur.fetchall()
    
    print("Campaign ID | Total | Score | Rationale | Images | LeadRec | Screen | Contact | Size | Brief")
    print("-" * 90)
    for row in results:
        print(f"{row[0]:<11} | {row[1]:<5} | {row[2]:<5} | {row[3]:<9} | {row[4]:<6} | {row[5]:<7} | {row[6]:<6} | {row[7]:<7} | {row[8]:<4} | {row[9]:<5}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    generate_report()
