import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console

console = Console()

DOMAIN_REGEX = re.compile(r"^(?:https?://)?([a-zA-Z0-9.\-*]+(?::\d+)?)(?:/.*)?$")


def is_redacted(domain: str, snippet: Optional[str] = None) -> bool:
    """Detect if a PublicWWW finding is masked/redacted."""
    if not domain:
        return True
    domain_clean = domain.strip().lower()
    if "*" in domain_clean or "<private>" in domain_clean or "upgrade" in domain_clean:
        return True
    if snippet and ("upgrade to view" in snippet.lower() or "upgrade" in snippet.lower()):
        return True
    return False


def clean_domain(domain_str: str) -> str:
    """Normalize domain string to apex registered domain (disabling subdomains)."""
    d = domain_str.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split(":")[0]
    import tldextract
    ext = tldextract.extract(d)
    top_domain = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
    if top_domain:
        return top_domain
    return d


def parse_csv_export(file_path: Path) -> List[Dict]:
    """Parse PublicWWW CSV export."""
    results = []
    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.lower().strip() if fn else "" for fn in (reader.fieldnames or [])]
        
        # Determine column aliases
        domain_col = next((fn for fn in reader.fieldnames if fn.lower().strip() in ("domain", "url", "site", "website", "host")), None)
        rank_col = next((fn for fn in reader.fieldnames if fn.lower().strip() in ("rank", "alexa_rank", "position")), None)
        snippet_col = next((fn for fn in reader.fieldnames if fn.lower().strip() in ("snippet", "code", "match", "content")), None)

        for row in reader:
            raw_domain = row.get(domain_col, "").strip() if domain_col else ""
            if not raw_domain:
                # Try fallback to first column
                raw_domain = list(row.values())[0].strip() if row.values() else ""

            if not raw_domain:
                continue

            raw_rank = row.get(rank_col, "").strip() if rank_col else None
            try:
                rank = int(raw_rank) if raw_rank else None
            except ValueError:
                rank = None

            snippet = row.get(snippet_col, "").strip() if snippet_col else None
            domain = clean_domain(raw_domain)
            visible = not is_redacted(raw_domain, snippet)

            results.append({
                "domain": domain,
                "rank": rank,
                "snippet": snippet,
                "visible": visible,
                "raw_domain": raw_domain,
            })
    return results


def parse_text_paste(content: str) -> List[Dict]:
    """Parse pasted text block line by line."""
    results = []
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Try space/tab/comma splitting for rank or domain
        parts = re.split(r"[\t,]+", line)
        raw_domain = parts[0].strip()
        raw_rank = None
        snippet = None

        if len(parts) > 1:
            if parts[1].strip().isdigit():
                raw_rank = int(parts[1].strip())
                snippet = parts[2].strip() if len(parts) > 2 else None
            else:
                snippet = parts[1].strip()

        domain = clean_domain(raw_domain)
        visible = not is_redacted(raw_domain, snippet)

        results.append({
            "domain": domain,
            "rank": raw_rank,
            "snippet": snippet,
            "visible": visible,
            "raw_domain": raw_domain,
        })
    return results


def save_findings_jsonl(new_records: List[Dict], findings_file: Path = Path("findings.jsonl")) -> None:
    """Save records to JSONL file with deduplication based on (domain, campaign_id, source)."""
    existing_records = []
    seen_keys = set()

    if findings_file.exists():
        with findings_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        key = (rec.get("domain"), rec.get("campaign_id"), rec.get("source"))
                        seen_keys.add(key)
                        existing_records.append(rec)
                    except json.JSONDecodeError:
                        pass

    added = 0
    for rec in new_records:
        key = (rec.get("domain"), rec.get("campaign_id"), rec.get("source"))
        if key not in seen_keys:
            seen_keys.add(key)
            existing_records.append(rec)
            added += 1

    with findings_file.open("w", encoding="utf-8") as f:
        for rec in existing_records:
            f.write(json.dumps(rec) + "\n")


def ingest_publicwww(
    campaign_id: str,
    file_path: Optional[Path] = None,
    paste_content: Optional[str] = None,
    findings_file: Path = Path("findings.jsonl"),
) -> List[Dict]:
    """Ingest PublicWWW findings and append to findings.jsonl with deduplication."""
    if file_path:
        if file_path.suffix.lower() == ".csv":
            raw_entries = parse_csv_export(file_path)
        else:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                raw_entries = parse_text_paste(f.read())
    elif paste_content:
        raw_entries = parse_text_paste(paste_content)
    else:
        raise ValueError("Must provide either file_path or paste_content for ingestion.")

    ingested_at = datetime.now(timezone.utc).isoformat()
    processed_records = []

    for entry in raw_entries:
        record = {
            "domain": entry["domain"],
            "rank": entry["rank"],
            "snippet": entry["snippet"],
            "visible": entry["visible"],
            "campaign_id": campaign_id,
            "ingested_at": ingested_at,
            "source": "publicwww",
        }
        processed_records.append(record)

    save_findings_jsonl(processed_records, findings_file=findings_file)

    visible_count = sum(1 for r in processed_records if r["visible"])
    redacted_count = len(processed_records) - visible_count
    console.print(
        f"[green]Ingested {len(processed_records)} records for campaign '{campaign_id}'[/green] "
        f"({visible_count} visible, {redacted_count} redacted) -> {findings_file}"
    )

from wp_hunter.ingest_abusech import fetch_urlhaus, fetch_threatfox


def ingest_abusech(
    campaign_id: str,
    urlhaus: bool = True,
    threatfox: bool = True,
    urlhaus_tag_filter: Optional[List[str]] = None,
    threatfox_malware_filter: Optional[List[str]] = None,
    threatfox_days: int = 7,
    findings_file: Path = Path("findings.jsonl"),
) -> List[Dict]:
    """Ingest Abuse.ch feeds (URLhaus, ThreatFox) into findings.jsonl."""
    records: List[Dict] = []
    if urlhaus:
        records.extend(fetch_urlhaus(campaign_id, tag_filter=urlhaus_tag_filter))
    if threatfox:
        records.extend(fetch_threatfox(campaign_id, malware_filter=threatfox_malware_filter, days=threatfox_days))

    if records:
        save_findings_jsonl(records, findings_file=findings_file)

    return records

