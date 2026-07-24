import os
import time
from typing import Dict, List, Optional
import httpx
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

VT_API_BASE = "https://www.virustotal.com/api/v3"


def get_vt_api_key() -> str:
    key = os.getenv("VT_API_KEY", "").strip()
    if not key:
        raise ValueError("VT_API_KEY not found in environment or .env file.")
    return key


class RateLimiter:
    """Simple rate limiter to respect VT free-tier (default 4 req/min)."""
    def __init__(self, requests_per_minute: float = 4.0):
        self.interval = 60.0 / requests_per_minute
        self.last_call = 0.0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.interval:
            sleep_time = self.interval - elapsed
            console.print(f"[dim]VT Rate Limiter: sleeping for {sleep_time:.1f}s...[/dim]")
            time.sleep(sleep_time)
        self.last_call = time.time()


def query_vt_file_hash(
    file_hash: str,
    api_key: str,
    limiter: RateLimiter,
    max_retries: int = 3,
) -> Optional[Dict]:
    """Query VirusTotal v3 GET /files/{hash} endpoint with retry logic."""
    headers = {"x-apikey": api_key, "User-Agent": "wp-hunter/0.1.0"}
    url = f"{VT_API_BASE}/files/{file_hash}"

    for attempt in range(max_retries + 1):
        limiter.wait()
        with httpx.Client(timeout=30.0) as client:
            res = client.get(url, headers=headers)

        if res.status_code == 429:
            err_text = res.text
            if "QuotaExceededError" in err_text:
                console.print("[bold yellow]VirusTotal API quota exceeded for this key (QuotaExceededError).[/bold yellow]")
                return {"_quota_exceeded": True}
            if attempt < max_retries:
                sleep_time = 60.0 * (attempt + 1)
                console.print(f"[yellow]VT Rate limit exceeded (429). Waiting {sleep_time:.0f}s (attempt {attempt + 1}/{max_retries})...[/yellow]")
                time.sleep(sleep_time)
                continue
            else:
                console.print(f"[red]VT Rate limit exceeded (429) after {max_retries} retries for hash {file_hash}.[/red]")
                return None

        if res.status_code == 404:
            console.print(f"[dim]Hash not found in VirusTotal: {file_hash}[/dim]")
            return None

        if res.status_code != 200:
            console.print(f"[red]VT API returned status {res.status_code} for hash {file_hash}: {res.text}[/red]")
            return None

        data = res.json().get("data", {})
        attrs = data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})

        return {
            "hash": file_hash,
            "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0),
            "undetected": stats.get("undetected", 0),
            "harmless": stats.get("harmless", 0),
            "name": attrs.get("meaningful_name") or (attrs.get("names", [None])[0] if attrs.get("names") else None),
            "type": attrs.get("type_description"),
            "source": "virustotal",
        }


def query_vt_contacted_domains(
    file_hash: str,
    api_key: str,
    limiter: RateLimiter,
) -> List[str]:
    """Fetch contacted domains for a file hash from VirusTotal."""
    limiter.wait()
    headers = {"x-apikey": api_key, "User-Agent": "wp-hunter/0.1.0"}
    url = f"{VT_API_BASE}/files/{file_hash}/contacted_domains"

    domains = []
    with httpx.Client(timeout=30.0) as client:
        res = client.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json().get("data", [])
            for item in data:
                domain_id = item.get("id")
                if domain_id:
                    domains.append(domain_id)
    return domains


def query_vt_domain_urls(
    domain: str,
    api_key: str,
    limiter: RateLimiter,
    limit: int = 40,
) -> List[str]:
    """
    GET /domains/{domain}/urls — fetch URL objects recently hosted on this domain.
    Returns a list of sha256 hashes of files served at those URLs.
    """
    limiter.wait()
    headers = {"x-apikey": api_key, "User-Agent": "wp-hunter/0.1.0"}
    url = f"{VT_API_BASE}/domains/{domain}/urls"
    params = {"limit": str(limit)}

    file_hashes = []
    with httpx.Client(timeout=30.0) as client:
        res = client.get(url, headers=headers, params=params)
        if res.status_code != 200:
            console.print(f"[dim]VT /domains/{domain}/urls: HTTP {res.status_code}[/dim]")
            return []
        for item in res.json().get("data", []):
            # Each item is a URL analysis object; extract last_http_response_content_sha256 if present
            attrs = item.get("attributes", {})
            content_sha256 = attrs.get("last_http_response_content_sha256")
            if isinstance(content_sha256, list):
                for f in content_sha256:
                    if f:
                        file_hashes.append(f)
            elif isinstance(content_sha256, str) and content_sha256:
                file_hashes.append(content_sha256)

            # Also grab sha256 from the URL's last analysis file directly
            fa = attrs.get("last_final_url", {})
            if isinstance(fa, dict) and fa.get("sha256"):
                file_hashes.append(fa["sha256"])
    return list(set(file_hashes))


def _fetch_contacted_domains_for_hash(
    file_hash: str,
    api_key: str,
    limiter: RateLimiter,
) -> List[str]:
    """Internal: fetch /files/{hash}/contacted_domains. Rate-limited."""
    limiter.wait()
    headers = {"x-apikey": api_key, "User-Agent": "wp-hunter/0.1.0"}
    url = f"{VT_API_BASE}/files/{file_hash}/contacted_domains"
    with httpx.Client(timeout=30.0) as client:
        res = client.get(url, headers=headers)
        if res.status_code != 200:
            return []
        return [item.get("id") for item in res.json().get("data", []) if item.get("id")]


def graph_walk_domain(
    seed_domain: str,
    campaign_id: str,
    api_key: str,
    limiter: RateLimiter,
    max_hashes: int = 10,
) -> List[Dict]:
    """
    Two-hop graph walk:
      seed_domain → files served (via /domains/{d}/urls) →
      sibling domains (via /files/{hash}/contacted_domains per file)

    Returns finding records with source="virustotal_graph".
    """
    console.print(f"[cyan]VT graph walk:[/cyan] seed domain [bold]{seed_domain}[/bold]")
    results = []

    # Hop 1: domain → file hashes
    hashes = query_vt_domain_urls(seed_domain, api_key, limiter)
    if not hashes:
        console.print(f"[dim]  No file hashes found for {seed_domain}[/dim]")
        return []

    console.print(f"[dim]  {len(hashes)} file hashes from domain URLs, walking up to {max_hashes}[/dim]")

    # Hop 2: file hashes → contacted / distributing domains
    seen_domains: set = {seed_domain}
    for h in hashes[:max_hashes]:
        sibling_domains = _fetch_contacted_domains_for_hash(h, api_key, limiter)
        for sib in sibling_domains:
            if sib not in seen_domains:
                seen_domains.add(sib)
                results.append({
                    "domain": sib,
                    "campaign_id": campaign_id,
                    "source": "virustotal_graph",
                    "graph_seed": seed_domain,
                    "pivot_hash": h,
                })

    console.print(f"[green]  VT graph: {len(results)} sibling domains discovered from {seed_domain}[/green]")
    return results


def pivot_vt_campaign(
    campaign_id: str,
    hashes: List[str],
    domains: List[str],
    pivot_contacted_domains: bool = False,
    graph_pivot: bool = False,
    rpm: float = 4.0,
) -> List[Dict]:
    """Pivot on VirusTotal for a campaign's hashes and domains."""
    if not hashes and not domains:
        return []

    api_key = get_vt_api_key()
    limiter = RateLimiter(requests_per_minute=rpm)
    results = []

    for h in hashes:
        console.print(f"[cyan]Querying VirusTotal for hash:[/cyan] [bold]{h}[/bold]")
        res = query_vt_file_hash(h, api_key, limiter)
        if res:
            if res.get("_quota_exceeded"):
                console.print("[yellow]Skipping remaining VirusTotal hash queries due to key quota limit.[/yellow]")
                break
            res["campaign_id"] = campaign_id
            results.append(res)

            if pivot_contacted_domains:
                contacted = query_vt_contacted_domains(h, api_key, limiter)
                for cd in contacted:
                    results.append({
                        "domain": cd,
                        "associated_hash": h,
                        "campaign_id": campaign_id,
                        "source": "virustotal_contacted_domain",
                    })

    # Graph pivot on seed domains
    if graph_pivot and domains:
        for seed in domains:
            console.print(f"[bold blue]Starting VT graph walk for seed domain:[/bold blue] {seed}")
            walked = graph_walk_domain(seed, campaign_id, api_key, limiter)
            results.extend(walked)

    return results
