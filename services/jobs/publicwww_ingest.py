import argparse
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discovery_helpers import get_conn, get_campaign_id, upsert_candidate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
logger = logging.getLogger("publicwww_ingest")

def ingest_report(json_path: str):
    logger.info("Starting ingestion from %s", json_path)
    
    if not os.path.exists(json_path):
        logger.error("File not found: %s", json_path)
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if not isinstance(data, list):
        logger.error("Expected JSON array in %s", json_path)
        sys.exit(1)
        
    conn = get_conn()
    try:
        # Assuming wp-remediation campaign id from helpers.
        campaign_id = get_campaign_id(conn)
        
        inserted = 0
        skipped = 0
        
        for item in data:
            domain = item.get("domain")
            if not domain or "***" in domain or not item.get("publicwww_visible", True):
                skipped += 1
                continue
                
            evidence = item
            query_used = f"publicwww:{item.get('campaign_id', 'unknown')}"
            
            ok = upsert_candidate(
                conn,
                campaign_id=campaign_id,
                domain=domain,
                source="publicwww",
                query_used=query_used,
                evidence=evidence
            )
            
            if ok:
                inserted += 1
                
        conn.commit()
        logger.info("Ingestion complete. Inserted: %d, Skipped/Masked: %d", inserted, skipped)
        
    except Exception as e:
        logger.exception("Ingestion failed")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest wp-hunter / seo-spam-hunter JSON reports")
    parser.add_argument("report_file", help="Path to report.json")
    args = parser.parse_args()
    
    ingest_report(args.report_file)
