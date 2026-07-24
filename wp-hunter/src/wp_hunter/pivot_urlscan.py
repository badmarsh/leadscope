import asyncio
import os
import time
from typing import Dict, List, Optional
import httpx
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

URLSCAN_API_BASE = "https://urlscan.io/api/v1"


def get_urlscan_api_key() -> str:
    key = os.getenv("URLSCAN_API_KEY", "").strip()
    if not key:
        raise ValueError("URLSCAN_API_KEY not found in environment or .env file.")
    return key


async def search_urlscan_query(
    query: str,
    api_key: str,
    max_pages: int = 10,
) -> List[Dict]:
    """Execute a urlscan.io search query with pagination and rate limit handling."""
    headers = {"API-Key": api_key, "User-Agent": "wp-hunter/0.1.0"}
    results = []
    search_after = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in range(max_pages):
            params: Dict[str, str] = {"q": query, "size": "100"}
            if search_after:
                params["search_after"] = search_after

            response = await client.get(
                f"{URLSCAN_API_BASE}/search/", headers=headers, params=params
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                console.print(f"[yellow]urlscan rate limited (429). Retrying in {retry_after}s...[/yellow]")
                await asyncio.sleep(retry_after)
                continue

            if response.status_code == 400:
                err_data = response.json() if response.content else {}
                err_msg = err_data.get("message", response.text)
                console.print(
                    f"[bold red]urlscan Search API Error 400 for query '{query}': {err_msg}[/bold red]\n"
                    "[dim]Note: Certain fields like `page.string` require urlscan Professional/Enterprise tiers.[/dim]"
                )
                break

            if response.status_code != 200:
                console.print(f"[red]urlscan API returned status {response.status_code}: {response.text}[/red]")
                break

            data = response.json()
            hits = data.get("results", [])
            if not hits:
                break

            for hit in hits:
                task = hit.get("task", {})
                page_info = hit.get("page", {})
                scan_id = hit.get("_id") or task.get("uuid")

                domain = page_info.get("domain") or task.get("domain") or page_info.get("apexDomain")
                if not domain and page_info.get("url"):
                    from wp_hunter.ingest import clean_domain
                    domain = clean_domain(page_info["url"])

                results.append({
                    "domain": domain,
                    "page_url": page_info.get("url") or task.get("url"),
                    "scan_id": scan_id,
                    "screenshot_url": f"https://urlscan.io/screenshots/{scan_id}.png" if scan_id else None,
                    "first_seen": task.get("time"),
                    "last_seen": task.get("time"),
                    "source": "urlscan",
                })

            has_more = data.get("has_more", False)
            if not has_more or len(hits) < 100:
                break

            # Set search_after from last hit
            last_sort = hits[-1].get("sort")
            if last_sort:
                search_after = ",".join(str(s) for s in last_sort)
            else:
                break

            await asyncio.sleep(1.0)  # Default rate limit floor

    return results


async def fetch_archived_sample(scan_id: str, api_key: str) -> Optional[Dict]:
    """Fetch archived scan result detail for analyst verification (no live request)."""
    headers = {"API-Key": api_key, "User-Agent": "wp-hunter/0.1.0"}
    url = f"{URLSCAN_API_BASE}/result/{scan_id}/"
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            return res.json()
        return None


def pivot_urlscan_campaign(
    campaign_id: str,
    pivot_queries: List[str],
    max_pages: int = 10,
) -> List[Dict]:
    """Pivot on urlscan for a campaign."""
    api_key = get_urlscan_api_key()
    all_findings = []

    for q in pivot_queries:
        console.print(f"[cyan]Executing urlscan pivot query:[/cyan] [bold]{q}[/bold]")
        findings = asyncio.run(search_urlscan_query(q, api_key, max_pages=max_pages))
        for f in findings:
            f["campaign_id"] = campaign_id
            f["query"] = q
        all_findings.extend(findings)

    console.print(f"[green]urlscan pivot found {len(all_findings)} hits for '{campaign_id}'[/green]")
    return all_findings
