import asyncio
from typing import Dict, List, Optional
import httpx
from rich.console import Console
from datetime import datetime

console = Console()

WAYBACK_CDX_API = "https://web.archive.org/cdx/search/cdx"


async def fetch_cdx_data(domain: str, match_mime: Optional[str] = None, max_retries: int = 3) -> List[List[str]]:
    """Fetch CDX data for a domain from the Wayback Machine."""
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "limit": "500",
        "fl": "timestamp,original,mimetype,statuscode",
        "collapse": "timestamp:6"  # Collapse by month (YYYYMM)
    }
    if match_mime:
        params["filter"] = f"mimetype:{match_mime}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                res = await client.get(WAYBACK_CDX_API, params=params)
                if res.status_code == 200:
                    data = res.json()
                    # First row is headers: ["timestamp", "original", "mimetype", "statuscode"]
                    return data[1:] if len(data) > 1 else []
                elif res.status_code == 429:
                    console.print(f"[yellow]Wayback API rate limited. Retrying in 5s...[/yellow]")
                    await asyncio.sleep(5)
                else:
                    console.print(f"[red]Wayback API returned status {res.status_code}[/red]")
                    break
            except httpx.RequestError as e:
                console.print(f"[red]Wayback API request error: {e}[/red]")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
    return []


def analyze_cdx_anomalies(cdx_rows: List[List[str]], match_mime: Optional[str]) -> Optional[str]:
    """
    Analyze CDX rows for anomalies.
    For Japanese Keyword Hack, we look for a sudden explosion of text/html pages 
    with weird paths. Here, we just look for the earliest timestamp where multiple
    distinct URLs start matching our criteria (or simply the first occurrence if match_mime).
    """
    if not cdx_rows:
        return None
    
    # Sort by timestamp (index 0)
    sorted_rows = sorted(cdx_rows, key=lambda x: x[0])
    
    # The earliest timestamp found is our rough infection date
    earliest_ts = sorted_rows[0][0]
    
    try:
        # Convert YYYYMMDDhhmmss to ISO date
        dt = datetime.strptime(earliest_ts, "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return earliest_ts


def pivot_wayback_domain(
    domain: str,
    campaign_id: str,
    match_mime: Optional[str] = None
) -> Optional[Dict]:
    """Pivot on Archive.org CDX API for a specific domain."""
    console.print(f"[cyan]Querying Wayback CDX for domain:[/cyan] [bold]{domain}[/bold]")
    cdx_rows = asyncio.run(fetch_cdx_data(domain, match_mime=match_mime))
    
    infection_date = analyze_cdx_anomalies(cdx_rows, match_mime)
    if infection_date:
        return {
            "domain": domain,
            "campaign_id": campaign_id,
            "source": "wayback",
            "infection_approx_date": infection_date,
            "cdx_hits": len(cdx_rows)
        }
    return None


def pivot_wayback_campaign(
    campaign_id: str,
    domains: List[str],
    match_mime: Optional[str] = None
) -> List[Dict]:
    """Run Wayback pivot on a list of domains."""
    results = []
    for d in set(domains):
        res = pivot_wayback_domain(d, campaign_id, match_mime)
        if res:
            results.append(res)
    console.print(f"[green]Wayback pivot found {len(results)} historical anomalies for '{campaign_id}'[/green]")
    return results
