"""
certstream_monitor.py — Stream Certificate Transparency logs via CertStream to find new WordPress targets.

Connects to CertStream WebSocket, filters for high-value TLD business domains,
optionally verifies WordPress via /wp-login.php, and upserts candidates.

Usage:
    python services/jobs/certstream_monitor.py
    python services/jobs/certstream_monitor.py --max-inserts 5
    python services/jobs/certstream_monitor.py --check-wp --max-inserts 10
"""
import argparse
import collections
import logging
import re
import requests
import sys
import os
import queue
import threading
import re
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discovery_helpers import get_conn, upsert_candidate, log_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
logger = logging.getLogger("certstream_monitor")

HIGH_VALUE_TLDS = {
    ".com", ".co.uk", ".com.au", ".ca", ".de", ".fr", ".nl",
    ".ch", ".at", ".be", ".se", ".no", ".dk", ".fi", ".ie",
    ".nz", ".sg", ".ae", ".lu", ".li", ".mc", ".sk", ".hu"
}

EXCLUDED_DOMAINS = {
    "cloudflare.com", "amazonaws.com", "azure.com", "pages.dev",
    "netlify.app", "vercel.app", "fastly.net", "github.io", "google.com"
}

def passes_heuristics(domain: str) -> bool:
    """Return True if domain matches target business profile."""
    if not any(domain.endswith(tld) for tld in HIGH_VALUE_TLDS):
        return False

    if any(ex in domain for ex in EXCLUDED_DOMAINS):
        return False

    # Check apex domain length
    parts = domain.split(".")
    name = parts[0]
    if len(name) < 4 or len(name) > 35:
        return False

    # Filter out IP-like names or subdomains
    if re.search(r"\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}", name) or re.search(r"^\d+$", name):
        return False

    # Simple vowel check to filter out random DGAs
    if not re.search(r"[aeiouy]", name):
        return False

    return True

# Campaigns that use dedicated search-API discovery (e.g. Tavily, PublicWWW).
# CertStream is a threat-intel feed and is not appropriate for business discovery.
# Domains found via CT logs will never be relevant leads for these pipelines.
CERTSTREAM_EXCLUDED_CAMPAIGNS = {
    "jenex-hu-hvac",       # Uses Tavily/keyword search; targets Hungarian HVAC trade specifically
    "shoe-photo-upgrade",  # Uses search APIs; targets e-commerce merchants specifically
}

def passes_campaign_heuristics(domain: str, campaign: dict) -> bool:
    slug = campaign["slug"]

    # Hard opt-out: campaigns with their own discovery pipelines
    if slug in CERTSTREAM_EXCLUDED_CAMPAIGNS:
        return False

    if slug == "crypto-scams":
        return any(x in domain for x in ["crypto", "coin", "token", "wallet", "nft", "web3", "defi"])

    return passes_heuristics(domain)

def check_wordpress(domain: str) -> bool:
    """Quick check to confirm if target site is running WordPress."""
    url = f"https://{domain}/wp-login.php"
    try:
        resp = requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        return resp.status_code == 200 and ("wordpress" in resp.text.lower() or "wp-login" in resp.text.lower())
    except Exception:
        return False

def start_certstream_monitor(max_inserts: int = 0, check_wp: bool = False):
    import certstream

    logger.info("Starting CertStream monitor (max_inserts=%d, check_wp=%s)", max_inserts, check_wp)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, slug, settings FROM campaigns WHERE status = 'active'")
        active_campaigns = cur.fetchall()
    
    if not active_campaigns:
        logger.warning("No active campaigns found. Exiting.")
        return

    seen_domains = collections.deque(maxlen=100000)
    seen_set = set()

    state = {"inserted": 0, "processed": 0}
    state_lock = threading.Lock()

    domain_queue = queue.Queue(maxsize=50000)

    # Separate queue for domains that passed the WP check and are ready to insert
    db_queue = queue.Queue(maxsize=50000)

    def http_worker():
        try:
            while True:
                item = domain_queue.get()
                if item is None:
                    break
                domain, all_domains = item
                
                for campaign in active_campaigns:
                    if not passes_campaign_heuristics(domain, campaign):
                        continue

                    campaign_check_wp = check_wp or campaign["slug"] == "wp-remediation"
                    
                    is_wp_confirmed = False
                    if campaign_check_wp:
                        is_wp_confirmed = check_wordpress(domain)
                        if not is_wp_confirmed:
                            continue

                    evidence = {
                        "cert_domains": all_domains,
                        "discovered_via": "certificate_transparency",
                        "is_wp_confirmed": is_wp_confirmed,
                    }

                    try:
                        db_queue.put_nowait((campaign["id"], campaign["slug"], domain, evidence))
                    except queue.Full:
                        pass
                domain_queue.task_done()
        except Exception as e:
            logger.error("HTTP Worker error: %s", e)

    def db_writer():
        worker_conn = get_conn()
        try:
            while True:
                item = db_queue.get()
                if item is None:
                    break
                
                campaign_id, campaign_slug, domain, evidence = item
                
                ok = upsert_candidate(
                    worker_conn,
                    campaign_id=campaign_id,
                    domain=domain,
                    source="certstream",
                    query_used="certstream:ct_log_new_cert",
                    evidence=evidence,
                )

                if ok:
                    with state_lock:
                        state["inserted"] += 1
                        inserted = state["inserted"]
                    worker_conn.commit()
                    logger.info("  ✓ [%d] CertStream candidate inserted for campaign %s: %s (WP confirmed: %s)", inserted, campaign_slug, domain, evidence["is_wp_confirmed"])

                    if max_inserts > 0 and inserted >= max_inserts:
                        logger.info("Reached maximum requested inserts (%d). Stopping CertStream listener.", max_inserts)
                        log_api_call(worker_conn, campaign_id=campaign_id, stage="discovery", provider="certstream", query_count=state["processed"])
                        worker_conn.commit()
                        os._exit(0)
                        
                db_queue.task_done()
        except Exception as e:
            logger.error("DB Writer error: %s", e)
        finally:
            worker_conn.close()

    # Start 100 HTTP workers and 1 DB writer
    num_workers = 100
    for _ in range(num_workers):
        t = threading.Thread(target=http_worker, daemon=True)
        t.start()
        
    writer_t = threading.Thread(target=db_writer, daemon=True)
    writer_t.start()

    def message_callback(message, context):
        if message['message_type'] == "heartbeat":
            return
            
        all_domains = []
        if message['message_type'] == "certificate_update":
            all_domains = message['data']['leaf_cert']['all_domains']
        elif message['message_type'] == "dns_entries":
            all_domains = message['data']
            
        if not all_domains:
            return
            
        with state_lock:
            state["processed"] += 1

        for raw_domain in all_domains:
            domain = raw_domain.lstrip("*.").lower().strip()

            if domain in seen_set:
                continue

            if len(seen_domains) == seen_domains.maxlen:
                oldest = seen_domains.popleft()
                seen_set.discard(oldest)

            seen_set.add(domain)
            seen_domains.append(domain)

            try:
                domain_queue.put_nowait((domain, all_domains))
            except queue.Full:
                pass

        if state["processed"] % 5000 == 0:
            logger.info("CertStream progress: %d cert domains evaluated | %d candidates inserted | queue size: %d", 
                        state["processed"], state["inserted"], domain_queue.qsize())

    try:
        certstream.listen_for_events(message_callback, url="ws://certstream-server:8080/domains-only")
    except KeyboardInterrupt:
        logger.info("CertStream monitor stopped by user.")
    finally:
        if not conn.closed:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CertStream CT log stream ingest")
    parser.add_argument("--max-inserts", type=int, default=0, help="Stop after N inserts (0 = run indefinitely)")
    parser.add_argument("--check-wp", action="store_true", help="Perform live HTTP check for /wp-login.php before inserting")
    args = parser.parse_args()

    start_certstream_monitor(max_inserts=args.max_inserts, check_wp=args.check_wp)
