"""
Stage 0 — Certificate Transparency log monitor.

Connects to a certstream WebSocket feed and filters for pharma-hack /
Japanese-keyword-hack domain patterns. Writes matching domains directly
into findings.jsonl as source="certstream".

Supported feeds (configure via CERTSTREAM_URL env var):
  - wss://certstream.calidog.io           (hosted, unreliable)
  - ws://localhost:4000                   (certstream-server-go self-hosted)
  - wss://certstream.dev/ct              (certstream.dev Rust server)

Usage:
    python -m seo_spam_hunter.stage0_ct --campaign <id> [--max-certs N] [--duration-seconds N]

Or via CLI:
    seo-spam-hunter ct-monitor --campaign <id>
"""
import asyncio
import json
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

# Default certstream.dev feed (more stable than calidog hosted)
DEFAULT_CERTSTREAM_URL = os.getenv("CERTSTREAM_URL", "wss://certstream.calidog.io")

# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

# Pharma / SEO spam patterns — common across pharma-hack and Japanese keyword hack
PHARMA_PATTERNS: List[re.Pattern] = [
    re.compile(r"viagra", re.IGNORECASE),
    re.compile(r"cialis", re.IGNORECASE),
    re.compile(r"pharmacy", re.IGNORECASE),
    re.compile(r"levitra", re.IGNORECASE),
    re.compile(r"xanax", re.IGNORECASE),
    re.compile(r"oxycodone", re.IGNORECASE),
    re.compile(r"tramadol", re.IGNORECASE),
    re.compile(r"pills?[-.]", re.IGNORECASE),
    re.compile(r"rx[-.]", re.IGNORECASE),
    re.compile(r"meds[-.]", re.IGNORECASE),
]

# Lookalike patterns for common brands (extend as needed)
LOOKALIKE_PATTERNS: List[re.Pattern] = [
    re.compile(r"paypa[l1]", re.IGNORECASE),
    re.compile(r"g[o0]{2}g[l1]e", re.IGNORECASE),
    re.compile(r"micr[o0]s[o0]ft", re.IGNORECASE),
    re.compile(r"app[l1]e[-.]", re.IGNORECASE),
    re.compile(r"amaz[o0]n[-.]", re.IGNORECASE),
]

ALL_PATTERNS = PHARMA_PATTERNS + LOOKALIKE_PATTERNS


def _matches_any(domain: str) -> Optional[str]:
    """Return the first matching pattern string, or None."""
    for pat in ALL_PATTERNS:
        if pat.search(domain):
            return pat.pattern
    return None


def _extract_domains_from_message(msg: dict) -> List[str]:
    """Extract registered apex domains (disabling subdomains) from a certstream message."""
    import tldextract
    domains: Set[str] = set()
    data = msg.get("data", {})

    leaf = data.get("leaf_cert", {})
    subject = leaf.get("subject", {})
    cn = subject.get("CN", "")
    if cn:
        raw = cn.lower().lstrip("*.")
        ext = tldextract.extract(raw)
        top = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
        if top:
            domains.add(top)
        elif raw:
            domains.add(raw)

    for san in leaf.get("all_domains", []):
        raw = san.lower().lstrip("*.")
        ext = tldextract.extract(raw)
        top = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
        if top:
            domains.add(top)
        elif raw:
            domains.add(raw)

    return list(domains)


async def _monitor_certstream(
    campaign_id: str,
    findings_file: Path,
    max_certs: Optional[int],
    duration_seconds: Optional[float],
    feed_url: str,
) -> int:
    """
    Connect to certstream WebSocket and filter for pharma/lookalike patterns.
    Returns the count of matching domains written to findings.jsonl.
    """
    try:
        import websockets  # noqa: PLC0415
    except ImportError:
        console.print(
            "[bold red]websockets package not installed. "
            "Run: pip install websockets>=12.0[/bold red]"
        )
        return 0

    console.print(f"[bold green]Stage 0 CT monitor connecting to:[/bold green] {feed_url}")
    console.print(
        f"[dim]Campaign: {campaign_id} | "
        f"Max certs: {max_certs if max_certs is not None else 'unlimited'} | "
        f"Duration: {duration_seconds if duration_seconds is not None else 'unlimited'}s[/dim]"
    )

    matched = 0
    processed = 0
    start_time = asyncio.get_event_loop().time()

    try:
        async with websockets.connect(feed_url, ping_interval=30, open_timeout=15) as ws:
            while True:
                # Check exit conditions
                if max_certs and processed >= max_certs:
                    console.print(f"[yellow]Reached --max-certs {max_certs}. Stopping.[/yellow]")
                    break
                if duration_seconds:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= duration_seconds:
                        console.print(f"[yellow]Reached --duration {duration_seconds}s. Stopping.[/yellow]")
                        break

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    msg = json.loads(raw)
                except asyncio.TimeoutError:
                    continue
                except json.JSONDecodeError:
                    continue

                if msg.get("message_type") != "certificate_update":
                    continue

                processed += 1
                domains = _extract_domains_from_message(msg)

                for domain in domains:
                    pattern_hit = _matches_any(domain)
                    if pattern_hit:
                        record = {
                            "domain": domain,
                            "campaign_id": campaign_id,
                            "source": "certstream",
                            "ct_pattern": pattern_hit,
                            "ingested_at": datetime.now(timezone.utc).isoformat(),
                            "visible": True,
                            "rank": None,
                            "snippet": None,
                        }
                        with findings_file.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(record) + "\n")
                        matched += 1
                        console.print(
                            f"[bold red]MATCH[/bold red] [cyan]{domain}[/cyan] "
                            f"— pattern: [yellow]{pattern_hit}[/yellow]"
                        )

    except OSError as exc:
        console.print(f"[red]WebSocket connection error: {exc}[/red]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Unexpected error in CT monitor: {exc}[/red]")

    console.print(
        f"\n[bold green]CT monitor done.[/bold green] "
        f"Processed {processed} certs | Matched {matched} domains → {findings_file}"
    )
    return matched


def run_ct_monitor(
    campaign_id: str,
    findings_file: Path = Path("findings.jsonl"),
    max_certs: Optional[int] = None,
    duration_seconds: Optional[float] = None,
    feed_url: str = DEFAULT_CERTSTREAM_URL,
) -> int:
    """Synchronous entry point for CLI integration."""
    return asyncio.run(
        _monitor_certstream(
            campaign_id=campaign_id,
            findings_file=findings_file,
            max_certs=max_certs,
            duration_seconds=duration_seconds,
            feed_url=feed_url,
        )
    )
