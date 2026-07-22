"""
kb_ingest.py — Knowledge Base Ingestion Pipeline.

Fetches Wordfence blog articles via RSS, uses Firecrawl to extract markdown,
analyzes the text using the LLM for `publicwww` malware signatures, and inserts
them into the `malware_signatures` table.
"""
import logging
import requests
import xml.etree.ElementTree as ET
import json

import config
import db
import cost_log
import llm
# Re-use the existing scrape function
import stage5

logger = logging.getLogger(__name__)

WORDFENCE_RSS_URL = "https://www.wordfence.com/feed/"
CAMPAIGN_ID = 3  # WP Remediation campaign

EXTRACT_PROMPT = """
You are a cybersecurity analyst building a threat intelligence knowledge base.
Read the following markdown content from a cybersecurity blog post about WordPress vulnerabilities.

Identify any specific 'publicwww' search queries or raw code snippets that the author provides for finding infected websites.
A publicwww query often looks like: "eval(base64_decode" or "function wpf_install" or something similar enclosed in quotes.

Extract all such signatures. For each signature, provide:
1. "snippet": The exact string to search for (e.g., "eval(base64_decode" or whatever is specified).
2. "malware_family": A short name for the malware or vulnerability (e.g., "Balada Injector", "Fake Ransomware", "XSS Plugin Vulnerability").
3. "confidence": "high" if it's explicitly recommended as a publicwww search query, "medium" if it's just a raw code snippet.

Return ONLY a valid JSON array of objects. Each object must have "snippet", "malware_family", and "confidence".
If no actionable signatures are found, return an empty JSON array: []
Do not include any prose outside the JSON.

Article Content:
{page_text}
"""

def fetch_recent_articles() -> list[dict]:
    """Fetch the Wordfence RSS feed and return a list of article dicts."""
    try:
        resp = requests.get(WORDFENCE_RSS_URL, timeout=15)
        resp.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(resp.content)
        articles = []
        namespaces = {'content': 'http://purl.org/rss/1.0/modules/content/'}
        # Find all <item> under <channel>
        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            content = item.find("content:encoded", namespaces)
            
            if title is not None and link is not None:
                articles.append({
                    "title": title.text,
                    "url": link.text,
                    "content": content.text if content is not None else ""
                })
        return articles
    except Exception as exc:
        logger.error("Failed to fetch Wordfence RSS: %s", exc)
        return []

def run() -> dict:
    """Run the Knowledge Base ingestion pipeline."""
    logger.info("Starting KB Ingestion...")
    articles = fetch_recent_articles()
    
    if not articles:
        return {"error": "Failed to fetch articles"}
        
    logger.info("Found %d articles in RSS feed.", len(articles))
    
    results = {
        "articles_processed": 0,
        "signatures_extracted": 0,
        "articles_skipped": 0,
        "errors": 0
    }
    
    with db.get_conn() as conn:
        for article in articles:
            url = article["url"]
            title = article["title"]
            page_text = article["content"]
            
            # 1. Check if already processed
            existing = db.fetchone(
                conn, 
                "SELECT 1 FROM kb_articles WHERE url = %s", 
                (url,)
            )
            if existing:
                results["articles_skipped"] += 1
                continue
                
            logger.info("Processing new article: %s", title)
            
            if not page_text:
                logger.warning("No content found in RSS for %s", url)
                results["errors"] += 1
                continue
                
            # 3. LLM Extraction
            try:
                prompt = EXTRACT_PROMPT.format(page_text=page_text[:15000]) # Pass up to 15k chars
                parsed, ti, to = llm.chat_json(prompt, temperature=0.1, model=config.KB_INGEST_MODEL)
                
                # Log cost against the WP Remediation campaign
                cost_log.log_call(
                    conn, "kb_ingest", "gemini",
                    campaign_id=CAMPAIGN_ID,
                    model=config.KB_INGEST_MODEL,
                    tokens_in=ti,
                    tokens_out=to,
                )
                
                if not isinstance(parsed, list):
                    logger.warning("LLM returned non-list output for %s", url)
                    parsed = []
                    
            except Exception as exc:
                logger.error("LLM extraction error for %s: %s", url, exc)
                results["errors"] += 1
                continue
                
            # 4. Save Signatures
            inserted_count = 0
            for sig in parsed:
                snippet = sig.get("snippet")
                family = sig.get("malware_family") or "Unknown"
                confidence = sig.get("confidence") or "medium"
                
                if not snippet:
                    continue
                    
                # Insert into malware_signatures
                try:
                    db.execute(
                        conn,
                        """
                        INSERT INTO malware_signatures (campaign_id, snippet, malware_family, source_url, confidence)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (campaign_id, snippet) DO NOTHING
                        """,
                        (CAMPAIGN_ID, snippet, family, url, confidence)
                    )
                    inserted_count += 1
                except Exception as e:
                    logger.warning("Failed to insert signature %r: %s", snippet, e)
            
            # 5. Mark article as processed
            try:
                db.execute(
                    conn,
                    """
                    INSERT INTO kb_articles (url, title, signatures_extracted)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (url, title, inserted_count)
                )
            except Exception as e:
                logger.error("Failed to insert kb_articles record for %s: %s", url, e)
                
            results["articles_processed"] += 1
            results["signatures_extracted"] += inserted_count
            logger.info("Extracted %d signatures from %s", inserted_count, title)

    logger.info("KB Ingestion complete: %s", results)
    return results

if __name__ == "__main__":
    print(run())
