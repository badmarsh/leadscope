import json
from pathlib import Path
import psycopg2
from psycopg2.extras import Json
import os

DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_USER = os.environ.get("POSTGRES_USER", "leadscope")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "leadscope_dev")
DB_NAME = os.environ.get("POSTGRES_DB", "leadscope")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        port=DB_PORT
    )

def ingest_findings(file_path: Path):
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get campaign mappings
    cursor.execute("SELECT id, slug FROM campaigns;")
    campaigns = {row[1]: row[0] for row in cursor.fetchall()}

    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                domain = data.get("domain")
                source = data.get("source", "publicwww")
                campaign_slug = data.get("campaign_id")
                
                campaign_id = campaigns.get(campaign_slug)
                if not campaign_id:
                    print(f"Skipping {domain}: Campaign slug '{campaign_slug}' not found in DB.")
                    continue
                
                # We need to map data to candidates table schema
                cursor.execute("""
                    INSERT INTO candidates (domain, source, status, campaign_id, evidence_data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (domain, campaign_id) DO NOTHING
                """, (domain, source, "new", campaign_id, Json(data)))
                
                count += cursor.rowcount
            except Exception as e:
                print(f"Error processing line: {line.strip()} - {e}")
                
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Successfully ingested {count} new records from {file_path}")

if __name__ == "__main__":
    base_dir = Path("c:/Users/marek/Documents/Jenex_AI")
    wp_hunter_findings = base_dir / "wp-hunter" / "findings.jsonl"
    seo_spam_hunter_findings = base_dir / "seo-spam-hunter" / "findings.jsonl"
    
    print("Ingesting WP Hunter findings...")
    ingest_findings(wp_hunter_findings)
    
    print("Ingesting SEO Spam Hunter findings...")
    ingest_findings(seo_spam_hunter_findings)
