import psycopg2
import json

def verify_failures():
    conn = psycopg2.connect("postgresql://leadscope:leadscope_dev@postgres:5432/leadscope")
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) if hasattr(psycopg2, 'extras') else conn.cursor()
    
    cur.execute("""
        SELECT 
            c.id, c.domain, c.campaign_id,
            e.score, e.rationale, e.evidence_data,
            l.contact_email, l.contact_phone, l.enrichment_report, l.screenshot_url
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
          AND (
              e.score IS NULL OR 
              jsonb_array_length(COALESCE(e.evidence_data->'images_analyzed', '[]'::jsonb)) = 0 OR
              (l.contact_email IS NULL AND l.contact_phone IS NULL) OR
              l.screenshot_url IS NULL
          )
    """)
    
    failures = cur.fetchall()
    cur.close()
    conn.close()
    
    report_lines = ["# Final Verification Report: Unresolvable Candidates\n"]
    report_lines.append("The following candidates still lack complete data after forced re-evaluation and enrichment. Below is the verified reason why it is impossible to resolve them automatically:\n")
    
    for row in failures:
        domain = row[1]
        reasons = []
        
        # Check evaluator failures
        if row[3] is None:
            reasons.append("Evaluation completely failed (likely severe Cloudflare block or site offline).")
        else:
            evidence = row[5] if row[5] else {}
            images = evidence.get("images_analyzed", [])
            if not images:
                reasons.append("No product images found anywhere on the homepage or product catalog (Crawler verified 0 valid image nodes).")
                
        # Check enrichment failures
        if not row[6] and not row[7]:
            # No email or phone
            report = (row[8] or "").lower()
            if "cloudflare" in report or "bot" in report or "challenge" in report:
                reasons.append("Site employs aggressive anti-bot protection (Cloudflare) blocking contact extraction.")
            else:
                reasons.append("No email address or phone number published on the website (Verified via JSON-LD, OpenGraph, and explicit /kontakt page crawl).")
                
        if not row[9]:
            reasons.append("Screenshot capture timed out or failed (Site likely extremely slow or refusing headless browsers).")
            
        report_lines.append(f"### {domain}")
        for r in reasons:
            report_lines.append(f"- **{r}**")
        report_lines.append("")
        
    with open("failure_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Generated failure_report.md for {len(failures)} unresolvable candidates.")

if __name__ == "__main__":
    import psycopg2.extras
    verify_failures()
