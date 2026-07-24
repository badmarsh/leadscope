"""
kb_ingest.py — Knowledge Base Ingestion Pipeline.

Fully consolidated, DB-driven intelligence ingestion engine.
Discovers active sources from `threat_intel_sources`, fetches RSS/scraping feeds,
full-scrapes new articles via Crawl4AI (`crawler_client`), extracts structured IoC signatures
via Gemini LLM (`llm.chat_json`), and upserts signatures into `malware_signatures` in a 'pending' state.
"""
import logging
import requests
import xml.etree.ElementTree as ET
import json
import re
from typing import Any

import config
import db
import cost_log
import llm
from crawler_client import crawler_scrape

logger = logging.getLogger(__name__)

THREAT_KEYWORDS = [
    "malware", "hack", "backdoor", "injector", "inject", "infected",
    "vulnerability", "exploit", "webshell", "redirect", "phishing",
    "supply chain", "ransomware", "skimmer", "crypto"
]

EXTRACT_PROMPT = """
You are a top-tier WordPress cybersecurity threat intelligence analyst.
Analyze this blog post or security advisory about a WordPress malware infection or vulnerability.

Your goal is to extract ACTIONABLE INDICATORS OF COMPROMISE that can be used to:
1. Automatically detect infected websites (scanner snippets)
2. Prove infection to a website owner (proof method)
3. Pitch cleanup services to hacked site owners (outreach)

Extract ALL signatures you find. For each, output a JSON object with these fields:
- "snippet": (string, REQUIRED) A SHORT, HIGHLY UNIQUE substring (ideally 20-50 characters) that uniquely identifies the infection. 
  CRITICAL: The snippet MUST be visible in the frontend HTML/JS/CSS DOM. Do NOT extract backend PHP code (`$vars`, `eval()`, `base64_decode` of PHP). PublicWWW and browser scrapers cannot see backend PHP code.
  CRITICAL: Must be at least 15 characters long and contain symbols/punctuation. Do NOT extract single generic words or names like "clickfix", "FilesMan", or "c99shell". You MUST extract the actual code pattern.
  Examples: "<script src=\\"hxxps://malicious.com", "eval(String.fromCharCode(", "<iframe src=\\"...hidden\\">", "window.location.href = \\"ses/index\\""
- "malware_family": (string) The name of the malware, campaign, or vulnerability.
- "confidence": (string) "high" if snippet is explicitly called out as an IoC or search query.
  "medium" if it's a code snippet found in the analysis. "low" if inferred.
- "sneakiness_tier": (string) One of: "S", "A", "B", "C"
  S = Completely invisible to owner (DB injection, encrypted payload, supply chain)
  A = Hard to find (file with random name, fake plugin, cron job)
  B = Subtle (modified core file, .htaccess redirect)
  C = Obvious (known plugin path, plain text malware)
- "proof_method": (string) How to gather UNDENIABLE PROOF of infection for the site owner.
  Examples: "Scan for base64 eval in PHP files", "Check Google Search Console for manual actions",
  "Use Google search: site:domain.com inurl:pharma", "Check /wp-content/uploads/ for PHP files"
- "outreach_hook": (string) A 1-sentence cold outreach hook referencing the specific infection.
  Example: "Your site is hosting a hidden backdoor that gives attackers full admin access."
- "outbreak_scope": (string) The scale of the campaign. Examples: "Over 10,000 sites", "Targeted", "Global"

Return ONLY a valid JSON array. If no actionable signatures found, return [].
Do not include any prose outside the JSON array.

Article Content:
{article_text}
"""

SCRAPING_INDEX_PROMPT = """
You are a cybersecurity intelligence analyst.
Below is the markdown text from a cybersecurity blog or security advisory index page.
Extract all URLs of individual blog posts or security advisories that discuss WordPress malware, vulnerabilities, or security incidents.

Return ONLY a valid JSON array of full URL strings. Example: ["https://example.com/blog/malware-attack-1", "https://example.com/blog/vulnerability-2"]
If no relevant article links are found, return [].

Page Markdown:
{index_text}
"""

def fetch_rss_items(feed_url: str) -> list[dict]:
    """Fetch RSS feed and return list of article dicts with title, url."""
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(feed_url, headers=headers, timeout=20)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title_node = item.find("title")
            link_node = item.find("link")

            title = title_node.text.strip() if title_node is not None and title_node.text else ""
            link = link_node.text.strip() if link_node is not None and link_node.text else ""

            if title and link:
                items.append({"title": title, "url": link})
    except Exception as exc:
        logger.error("Failed to fetch/parse RSS from %s: %s", feed_url, exc)
    return items

def extract_article_links_from_index(index_url: str, campaign_id: int, conn) -> list[dict]:
    """Scrape an index page and use LLM to discover article links."""
    logger.info("Scraping index page for discovery: %s", index_url)
    index_text, _ = crawler_scrape(index_url, force_playwright=False)
    if not index_text:
        logger.warning("Failed to crawl index page: %s", index_url)
        return []

    try:
        if len(index_text) > 20000:
            logger.warning("Index text truncated to 20,000 characters for LLM prompt")
        prompt = SCRAPING_INDEX_PROMPT.format(index_text=index_text[:20000])
        parsed, ti, to = llm.chat_json(prompt, temperature=0.1, model=config.KB_INGEST_MODEL)
        cost_log.log_call(
            conn, "kb_ingest_index", "gemini",
            campaign_id=campaign_id,
            model=config.KB_INGEST_MODEL,
            tokens_in=ti, tokens_out=to
        )
        if isinstance(parsed, list):
            return [{"title": "Discovered Article", "url": u} for u in parsed if isinstance(u, str) and u.startswith("http")]
    except Exception as exc:
        logger.error("Failed to extract links from index page %s: %s", index_url, exc)
    return []

def fetch_github_files(api_url: str) -> list[dict]:
    """Fetch file contents from a GitHub repository via API."""
    items = []
    import re
    import os
    try:
        match = re.search(r"repos/([^/]+)/([^/]+)", api_url)
        if not match:
            logger.error("Invalid github API URL: %s", api_url)
            return []
        
        owner, repo = match.groups()
        headers = {"User-Agent": "Mozilla/5.0"}
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"
            
        resp = requests.get(api_url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        tree = data.get("tree", [])
        for node in tree:
            if node.get("type") == "blob":
                path = node.get("path", "")
                if path.endswith(".php") or path.endswith(".js"):
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"
                    items.append({"title": f"GitHub File: {path}", "url": raw_url})
    except Exception as exc:
        logger.error("Failed to fetch github files from %s: %s", api_url, exc)
        
    return items

def run() -> dict:
    """Run the consolidated Knowledge Base ingestion pipeline."""
    logger.info("Starting Consolidated KB Ingestion...")

    stats = {
        "sources_checked": 0,
        "articles_processed": 0,
        "articles_skipped": 0,
        "signatures_extracted": 0,
        "errors": 0
    }

    with db.get_conn() as conn:
        conn.autocommit = False
        # Resolve campaign_id
        campaign_row = db.fetchone(conn, "SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
        if not campaign_row:
            raise RuntimeError("Campaign 'wp-remediation' not found in DB — cannot ingest.")
        campaign_id = campaign_row["id"]

        # 1. Fetch active threat intel sources
        sources = db.fetchall(conn, "SELECT id, name, url, type FROM threat_intel_sources WHERE status = 'active'")
        stats["sources_checked"] = len(sources)
        logger.info("Found %d active threat intel sources in DB", len(sources))

        for source in sources:
            source_id = source["id"]
            source_name = source["name"]
            source_url = source["url"]
            source_type = source["type"]

            logger.info("--- Processing Source #%s: %s (%s) ---", source_id, source_name, source_type)

            # Get candidate article links
            articles = []
            if source_type in ("rss", "api"):
                articles = fetch_rss_items(source_url)
            elif source_type == "scraping":
                articles = extract_article_links_from_index(source_url, campaign_id, conn)
            elif source_type == "github":
                articles = fetch_github_files(source_url)

            logger.info("Source '%s' returned %d candidate articles", source_name, len(articles))

            for article in articles:
                url = article["url"]
                title = article.get("title", "")

                try:
                    # 2. Check if already processed
                    existing = db.fetchone(conn, "SELECT 1 FROM kb_articles WHERE url = %s", (url,))
                    if existing:
                        stats["articles_skipped"] += 1
                        continue

                    # 3. Relevance Filter (for RSS)
                    if source_type == "rss" and title:
                        title_lower = title.lower()
                        is_relevant = any(kw in title_lower for kw in THREAT_KEYWORDS)
                        if not is_relevant:
                            logger.info("Skipping non-threat article: %s", title)
                            stats["articles_skipped"] += 1
                            continue

                    logger.info("Processing new article: %s (%s)", title or url, url)

                    # 4. Full Article Scrape via Crawl4AI
                    if source_type == "github":
                        try:
                            resp = requests.get(url, timeout=15)
                            resp.raise_for_status()
                            page_text = resp.text
                        except Exception as e:
                            logger.error("Failed to fetch github raw content %s: %s", url, e)
                            page_text = ""
                    else:
                        page_text, _ = crawler_scrape(url, force_playwright=False)
                        
                    if not page_text or len(page_text.strip()) < 100:
                        logger.warning("Crawler returned insufficient text for %s", url)
                        stats["errors"] += 1
                        continue

                    # 5. LLM Extraction
                    prompt = EXTRACT_PROMPT.format(article_text=page_text[:25000])
                    parsed, ti, to = llm.chat_json(prompt, temperature=0.1, model=config.KB_INGEST_MODEL)

                    cost_log.log_call(
                        conn, "kb_ingest", "gemini",
                        campaign_id=campaign_id,
                        model=config.KB_INGEST_MODEL,
                        tokens_in=ti, tokens_out=to
                    )

                    if not isinstance(parsed, list):
                        logger.warning("LLM returned non-list output for %s: %s", url, type(parsed))
                        parsed = []

                    # 6. Insert Signatures
                    inserted_count = 0
                    for sig in parsed:
                        if not isinstance(sig, dict):
                            continue

                        snippet = sig.get("snippet")
                        if not snippet or not isinstance(snippet, str):
                            continue

                        snippet_clean = snippet.strip()
                        
                        # STRICT VALIDATION:
                        # 1. Must be at least 15 characters
                        # 2. Cannot exceed 2000 characters
                        # 3. Must contain at least one special character (space doesn't count) to ensure it's actual code/URL and not just a single word
                        # 4. Must not be purely alphanumeric (which covers generic words like "clickfix", "FilesMan", etc)
                        if len(snippet_clean) < 15 or len(snippet_clean) > 2000:
                            logger.info("Discarding snippet for length violation: %s", snippet_clean)
                            continue
                            
                        if re.match(r'^[A-Za-z0-9\s]+$', snippet_clean):
                            logger.info("Discarding snippet for being purely alphanumeric/generic: %s", snippet_clean)
                            continue

                        family = sig.get("malware_family") or "Unknown"
                        confidence = sig.get("confidence") or "medium"
                        sneakiness = sig.get("sneakiness_tier") or "C"
                        proof_method = sig.get("proof_method")
                        outreach_hook = sig.get("outreach_hook")
                        outbreak_scope = sig.get("outbreak_scope") or "global"

                        try:
                            db.execute(
                                conn,
                                """
                                INSERT INTO malware_signatures
                                    (campaign_id, snippet, malware_family, source_url, confidence,
                                     sneakiness_tier, proof_method, outreach_hook, outbreak_scope, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                                ON CONFLICT (campaign_id, snippet) DO UPDATE SET
                                    malware_family  = EXCLUDED.malware_family,
                                    confidence      = EXCLUDED.confidence,
                                    sneakiness_tier = EXCLUDED.sneakiness_tier,
                                    proof_method    = EXCLUDED.proof_method,
                                    outreach_hook   = EXCLUDED.outreach_hook,
                                    outbreak_scope  = EXCLUDED.outbreak_scope,
                                    source_url      = EXCLUDED.source_url
                                """,
                                (campaign_id, snippet_clean, family, url, confidence,
                                 sneakiness, proof_method, outreach_hook, outbreak_scope)
                            )
                            inserted_count += 1
                        except Exception as e:
                            logger.warning("Failed to insert signature %r: %s", snippet_clean[:50], e)

                    # 7. Article Tracking
                    db.execute(
                        conn,
                        """
                        INSERT INTO kb_articles (url, title, signatures_extracted)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (url) DO NOTHING
                        """,
                        (url, title or url, inserted_count)
                    )

                    stats["articles_processed"] += 1
                    stats["signatures_extracted"] += inserted_count
                    logger.info("Extracted %d signatures from %s", inserted_count, title or url)
                    conn.commit()

                except Exception as article_exc:
                    conn.rollback()
                    logger.error("Error processing article %s: %s", url, article_exc)
                    stats["errors"] += 1

            # 8. Update Source Timestamp
            db.execute(
                conn,
                "UPDATE threat_intel_sources SET last_checked_at = now() WHERE id = %s",
                (source_id,)
            )
            conn.commit()

    logger.info("KB Ingestion complete: %s", stats)
    return stats

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
    res = run()
    print(res)
