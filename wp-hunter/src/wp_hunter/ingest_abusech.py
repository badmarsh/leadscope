"""
Abuse.ch feed ingest — URLhaus and ThreatFox.

Both feeds are free, no API key required.
Produces findings.jsonl records with source="urlhaus" or source="threatfox".
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from rich.console import Console

console = Console()

URLHAUS_RECENT_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/limit/1000/"
THREATFOX_RECENT_URL = "https://threatfox-api.abuse.ch/api/v1/"

# Tags that indicate a compromised WordPress site being used as a malware loader
WORDPRESS_TAGS = {"wordpress", "compromised", "wp", "cmswordpress"}


def _extract_domain(url_str: str) -> Optional[str]:
    """Strip scheme and path to return bare domain."""
    try:
        url_str = url_str.strip()
        url_str = url_str.split("//", 1)[-1]  # drop scheme
        url_str = url_str.split("/")[0]        # drop path
        url_str = url_str.split(":")[0]        # drop port
        return url_str.lower() if url_str else None
    except Exception:
        return None


def fetch_urlhaus(
    campaign_id: str,
    tag_filter: Optional[List[str]] = None,
    timeout: float = 30.0,
) -> List[Dict]:
    """
    Fetch recent URLhaus entries and return normalised finding records.

    Args:
        campaign_id: Campaign ID to stamp on each record.
        tag_filter: If provided, only include URLs whose tags overlap with this list.
                    Pass None to include all URLs tagged with any WordPress indicator.
    Returns:
        List of finding dicts ready to write to findings.jsonl.
    """
    effective_tags = {t.lower() for t in (tag_filter or [])} | WORDPRESS_TAGS

    console.print("[bold blue]Fetching URLhaus recent feed...[/bold blue]")
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "wp-hunter/0.1.0"}) as client:
            resp = client.post(URLHAUS_RECENT_URL, data={"query": "get_urls"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        console.print(f"[red]URLhaus fetch failed: {exc}[/red]")
        return []

    data = resp.json()
    if data.get("query_status") != "ok":
        console.print(f"[yellow]URLhaus returned non-ok status: {data.get('query_status')}[/yellow]")
        return []

    ingested_at = datetime.now(timezone.utc).isoformat()
    records = []
    raw_urls = data.get("urls", [])

    for entry in raw_urls:
        entry_tags = {t.lower() for t in (entry.get("tags") or [])}
        # Accept if any WordPress indicator present in tags, or no filter applied
        if not (entry_tags & effective_tags):
            continue

        url_str = entry.get("url", "")
        domain = _extract_domain(url_str)
        if not domain:
            continue

        records.append({
            "domain": domain,
            "url": url_str,
            "campaign_id": campaign_id,
            "source": "urlhaus",
            "urlhaus_id": entry.get("id"),
            "urlhaus_status": entry.get("url_status"),
            "urlhaus_tags": list(entry_tags),
            "threat": entry.get("threat"),
            "date_added": entry.get("date_added"),
            "ingested_at": ingested_at,
            "visible": True,
            "rank": None,
            "snippet": None,
        })

    console.print(
        f"[green]URLhaus: {len(records)} WordPress-tagged records for campaign '{campaign_id}'[/green]"
    )
    return records


def fetch_threatfox(
    campaign_id: str,
    malware_filter: Optional[List[str]] = None,
    days: int = 7,
    timeout: float = 30.0,
) -> List[Dict]:
    """
    Fetch recent ThreatFox IOCs and return normalised finding records.

    Args:
        campaign_id: Campaign ID to stamp on each record.
        malware_filter: If provided, only include IOCs whose malware name contains
                        one of these substrings (case-insensitive). E.g. ['wordpress', 'wp'].
                        Pass None to include all URL-type IOCs.
        days: Look back this many days (max 90 per ThreatFox API).
    Returns:
        List of finding dicts ready to write to findings.jsonl.
    """
    console.print(f"[bold blue]Fetching ThreatFox IOCs (last {days} days)...[/bold blue]")
    payload = json.dumps({"query": "get_iocs", "days": min(days, 90)})

    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "wp-hunter/0.1.0"}) as client:
            resp = client.post(
                THREATFOX_RECENT_URL,
                content=payload,
                headers={"Content-Type": "application/json", "User-Agent": "wp-hunter/0.1.0"},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        console.print(f"[red]ThreatFox fetch failed: {exc}[/red]")
        return []

    data = resp.json()
    if data.get("query_status") != "ok":
        console.print(f"[yellow]ThreatFox returned non-ok status: {data.get('query_status')}[/yellow]")
        return []

    mf_lower = [f.lower() for f in (malware_filter or [])]
    ingested_at = datetime.now(timezone.utc).isoformat()
    records = []

    for ioc in data.get("data", []):
        # Only process URL-type IOCs
        ioc_type = ioc.get("ioc_type", "")
        if ioc_type not in ("url", "domain"):
            continue

        malware = (ioc.get("malware") or "").lower()
        if mf_lower and not any(f in malware for f in mf_lower):
            continue

        ioc_value = ioc.get("ioc", "")
        domain = _extract_domain(ioc_value) if ioc_type == "url" else ioc_value.lower().strip()
        if not domain:
            continue

        records.append({
            "domain": domain,
            "url": ioc_value if ioc_type == "url" else None,
            "campaign_id": campaign_id,
            "source": "threatfox",
            "threatfox_id": ioc.get("id"),
            "threatfox_malware": ioc.get("malware"),
            "threatfox_malware_printable": ioc.get("malware_printable"),
            "threatfox_confidence": ioc.get("confidence_level"),
            "threat_type": ioc.get("threat_type"),
            "first_seen": ioc.get("first_seen"),
            "ingested_at": ingested_at,
            "visible": True,
            "rank": None,
            "snippet": None,
        })

    console.print(
        f"[green]ThreatFox: {len(records)} URL/domain IOC records for campaign '{campaign_id}'[/green]"
    )
    return records
