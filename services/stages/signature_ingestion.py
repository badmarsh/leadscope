import os
import sys
import json
# DEPRECATED: This file is superseded by services/stages/kb_ingest.py
# It can be safely deleted after the new kb_ingest.py is validated in production.

import logging
import requests
import psycopg2
from pydantic import BaseModel
from typing import List, Optional
from google import genai
from google.genai import types
import services.common.config as config

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
FIRECRAWL_ENDPOINT = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
GEMINI_PROXY_ENDPOINT = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://127.0.0.1:8045/v1")
GEMINI_PROXY_API_KEY = os.environ.get("GEMINI_PROXY_API_KEY", "dummy")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

class Signature(BaseModel):
    snippet: str
    malware_family: Optional[str]
    confidence: str
    proof_method: Optional[str]
    outreach_hook: Optional[str]
    outbreak_scope: str = "global"

class ExtractionResult(BaseModel):
    signatures: List[Signature]

def scrape_with_firecrawl(url: str) -> str:
    """Scrape the given URL using Firecrawl and return markdown text. If it's a local file, read it."""
    if url.startswith("file://"):
        path = url[7:]
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    if not FIRECRAWL_API_KEY:
        logger.warning("No FIRECRAWL_API_KEY, falling back to basic requests/BeautifulSoup...")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'html.parser')
        # Simple extraction of text
        return soup.get_text(separator='\n', strip=True)

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"url": url, "formats": ["markdown"]}
    
    endpoint = FIRECRAWL_ENDPOINT
    if not endpoint.endswith("/v1/scrape"):
        endpoint = f"{endpoint.rstrip('/')}/v1/scrape"

    r = requests.post(endpoint, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("success") and "data" in data and "markdown" in data["data"]:
        return data["data"]["markdown"]
    else:
        raise Exception(f"Firecrawl scrape failed: {data}")

from openai import OpenAI

def extract_signatures(markdown: str) -> tuple[List[Signature], int, int]:
    """Use Gemini 3 Flash to extract code snippets and metadata."""
    client = OpenAI(
        api_key=GEMINI_PROXY_API_KEY,
        base_url=f"{GEMINI_PROXY_ENDPOINT}/v1" if not GEMINI_PROXY_ENDPOINT.endswith("/v1") else GEMINI_PROXY_ENDPOINT
    )

    prompt = f"""
    You are a cybersecurity expert analyzing a blog post about WordPress malware.
    Extract any malicious PHP, JavaScript, or bash code snippets (signatures) mentioned in the text.
    For each snippet:
    - 'snippet': the exact malicious code block. Must be actual code, not prose.
    - 'malware_family': the name of the malware or vulnerability (if mentioned), else null.
    - 'confidence': 'high' (obvious malware), 'medium', or 'low'.
    - 'proof_method': The best way to gather undeniable proof of this infection (e.g., 'google_serp_spam', 'cloaked_redirect', 'exposure_scan').
    - 'outreach_hook': A compelling 1-sentence hook to use in cold email (e.g., "Your customers are being redirected to scam sites.").
    - 'outbreak_scope': The scope of this malware campaign (e.g., 'global', 'targeted', 'emerging').
    
    Respond in JSON matching this schema:
    {ExtractionResult.model_json_schema()}

    Blog post content:
    ---
    {markdown[:30000]}  # limit length just in case
    """

    response = client.chat.completions.create(
        model=config.GEMINI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}
    )

    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    try:
        content = response.choices[0].message.content
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        result = ExtractionResult.model_validate_json(content)
        return result.signatures, tokens_in, tokens_out
    except Exception as e:
        content = response.choices[0].message.content if response.choices else "No content"
        logger.warning("Failed to parse LLM output: %s\nRaw output: %s", e, content)
        return [], tokens_in, tokens_out

def ingest_url(url: str):
    logger.info("\nIngesting %s...", url)
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
    row = cur.fetchone()
    if not row:
        logger.error("wp-remediation campaign not found in DB.")
        conn.close()
        return
    campaign_id = row[0]

    try:
        markdown = scrape_with_firecrawl(url)
    except Exception as e:
        logger.warning("Scrape failed: %s", e)
        conn.close()
        return

    logger.info("Scraped %s chars. Extracting signatures...", len(markdown))
    signatures, tokens_in, tokens_out = extract_signatures(markdown)
    
    inserted_count = 0
    for sig in signatures:
        if not sig.snippet or len(sig.snippet) < 5 or len(sig.snippet) > 5000:
            continue
        db_url = url.replace("file://", "http://") if url.startswith("file://") else url
        cur.execute("""
            INSERT INTO malware_signatures (campaign_id, snippet, malware_family, source_url, confidence, sneakiness_tier, proof_method, outreach_hook, outbreak_scope)
            VALUES (%s, %s, %s, %s, %s, 'S', %s, %s, %s)
            ON CONFLICT (campaign_id, snippet) DO UPDATE 
            SET sneakiness_tier = 'S', 
                proof_method = EXCLUDED.proof_method, 
                outreach_hook = EXCLUDED.outreach_hook, 
                outbreak_scope = EXCLUDED.outbreak_scope
        """, (campaign_id, sig.snippet, sig.malware_family, db_url, sig.confidence, sig.proof_method, sig.outreach_hook, sig.outbreak_scope))
        if cur.rowcount > 0:
            inserted_count += 1
            logger.info("  + Inserted snippet (family: %s, tier: S)", sig.malware_family)

    cost = (tokens_in / 1_000_000 * 0.10) + (tokens_out / 1_000_000 * 0.40)
    
    cur.execute("""
        INSERT INTO api_call_log (campaign_id, stage, provider, model, tokens_in, tokens_out, cost_estimate_usd)
        VALUES (%s, 'signature_ingestion', 'gemini', 'gemini-3-flash', %s, %s, %s)
    """, (campaign_id, tokens_in, tokens_out, cost))

    logger.info("Done. Extracted %s total, inserted %s new. Logged API call (%s in / %s out).", len(signatures), inserted_count, tokens_in, tokens_out)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    urls = sys.argv[1:]
    if not urls:
        print("Usage: python signature_ingestion.py <url1> [url2] ...")
        sys.exit(1)
    for u in urls:
        ingest_url(u)
