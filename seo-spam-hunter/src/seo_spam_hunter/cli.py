import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from seo_spam_hunter.cluster import generate_clusters, generate_edge_list
from seo_spam_hunter.ingest import ingest_abusech, ingest_publicwww
from seo_spam_hunter.merge import merge_findings
from seo_spam_hunter.pivot_urlscan import pivot_urlscan_campaign
from seo_spam_hunter.pivot_vt import pivot_vt_campaign
from seo_spam_hunter.pivot_wayback import pivot_wayback_campaign
from seo_spam_hunter.report import generate_reports
from seo_spam_hunter.schema import freshness_gate, load_campaigns
from seo_spam_hunter.stage0_ct import DEFAULT_CERTSTREAM_URL, run_ct_monitor

app = typer.Typer(help="Advanced WordPress SEO Spam & Backdoor Hunting Pipeline")
console = Console()
FINDINGS_FILE = Path("findings.jsonl")


def _read_findings() -> list[dict]:
    if not FINDINGS_FILE.exists():
        return []
    res = []
    with FINDINGS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                res.append(json.loads(line))
    return res


def _write_findings(findings: list[dict]):
    with FINDINGS_FILE.open("a", encoding="utf-8") as f:
        for rec in findings:
            f.write(json.dumps(rec) + "\n")


@app.command()
def ingest(
    campaign: str = typer.Option(..., help="Campaign ID to ingest for"),
    file: Optional[Path] = typer.Option(None, help="Path to PublicWWW CSV or text paste"),
    force_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass freshness gate"),
):
    """Stage A: Ingest findings from PublicWWW."""
    campaigns = load_campaigns()
    target = next((c for c in campaigns if c.id == campaign), None)
    if not target:
        console.print(f"[bold red]Campaign '{campaign}' not found in campaigns.yaml[/bold red]")
        raise typer.Exit(1)

    freshness_gate([target], force_stale=force_stale)
    ingest_publicwww(campaign_id=campaign, file_path=file, findings_file=FINDINGS_FILE)


@app.command()
def ingest_feeds(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign ID"),
    urlhaus: bool = typer.Option(True, help="Fetch URLhaus recent feed"),
    threatfox: bool = typer.Option(True, help="Fetch ThreatFox recent IOCs"),
    threatfox_days: int = typer.Option(7, "--threatfox-days", help="ThreatFox look-back window (max 90)"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale"),
):
    """Stage A (feeds): Pull URLhaus and ThreatFox candidate domains into findings.jsonl."""
    campaigns = load_campaigns(config)
    camp = next((c for c in campaigns if c.id == campaign), None)
    if not camp:
        console.print(f"[bold red]Campaign '{campaign}' not found[/bold red]")
        raise typer.Exit(1)

    try:
        freshness_gate([camp], force_stale=i_know_this_is_stale)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(1)

    records = ingest_abusech(
        campaign_id=campaign,
        urlhaus=urlhaus,
        threatfox=threatfox,
        threatfox_days=threatfox_days,
        findings_file=FINDINGS_FILE,
    )
    console.print(f"[bold green]Ingested {len(records)} Abuse.ch records for '{campaign}'.[/bold green]")


@app.command()
def ct_monitor(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign ID to tag matches with"),
    max_certs: Optional[int] = typer.Option(None, "--max-certs", help="Stop after processing N certs (default: run until Ctrl-C)"),
    duration: Optional[float] = typer.Option(None, "--duration", help="Stop after N seconds (default: run until Ctrl-C)"),
    feed_url: str = typer.Option(DEFAULT_CERTSTREAM_URL, "--feed-url", help="certstream WebSocket URL"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale"),
):
    """
    Stage 0: Monitor Certificate Transparency logs for pharma/lookalike domains.

    Connects to a certstream WebSocket feed and writes matching domains into
    findings.jsonl in real-time. Run before Stage A ingest to catch newly
    registered malicious domains before search engines index them.

    Recommended feeds (set via --feed-url or CERTSTREAM_URL env var):
      wss://certstream.calidog.io           (hosted, unreliable)
      ws://localhost:4000                   (certstream-server-go, self-hosted)
      wss://certstream.dev/ct              (certstream.dev Rust server)
    """
    campaigns = load_campaigns(config)
    camp = next((c for c in campaigns if c.id == campaign), None)
    if not camp:
        console.print(f"[bold red]Campaign '{campaign}' not found[/bold red]")
        raise typer.Exit(1)

    try:
        freshness_gate([camp], force_stale=i_know_this_is_stale)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(1)

    console.print(
        "[bold yellow]Stage 0 CT Monitor — Press Ctrl-C to stop cleanly.[/bold yellow]"
    )
    run_ct_monitor(
        campaign_id=campaign,
        findings_file=FINDINGS_FILE,
        max_certs=max_certs,
        duration_seconds=duration,
        feed_url=feed_url,
    )


@app.command()
def pivot(
    campaign: str = typer.Option(..., help="Campaign ID to pivot on"),
    urlscan: bool = typer.Option(True, help="Enable URLScan pivot"),
    virustotal: bool = typer.Option(True, help="Enable VirusTotal pivot"),
    vt_graph: bool = typer.Option(False, "--vt-graph", help="Enable VT graph-walk pivot on seed domains"),
    wayback: bool = typer.Option(False, help="Enable Archive.org CDX pivot"),
    force_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass freshness gate"),
):
    """Stage B: Pivot on enriched intelligence sources."""
    campaigns = load_campaigns()
    target = next((c for c in campaigns if c.id == campaign), None)
    if not target:
        console.print(f"[bold red]Campaign '{campaign}' not found[/bold red]")
        raise typer.Exit(1)

    freshness_gate([target], force_stale=force_stale)

    existing = _read_findings()
    # Unique domains across this campaign's existing findings
    domains = list({f["domain"] for f in existing if f.get("campaign_id") == campaign and f.get("domain")})
    new_findings = []

    if urlscan and target.urlscan_pivot:
        console.print("[bold blue]Starting urlscan pivot...[/bold blue]")
        res = pivot_urlscan_campaign(campaign_id=campaign, pivot_queries=target.urlscan_pivot)
        new_findings.extend(res)

    if virustotal and (target.virustotal_pivot.hashes or target.virustotal_pivot.domains):
        console.print("[bold blue]Starting VirusTotal pivot...[/bold blue]")
        res = pivot_vt_campaign(
            campaign_id=campaign,
            hashes=target.virustotal_pivot.hashes,
            domains=target.virustotal_pivot.domains,
            graph_pivot=vt_graph,
        )
        new_findings.extend(res)

    if wayback and target.wayback_pivot.enabled:
        console.print("[bold blue]Starting Archive.org CDX pivot...[/bold blue]")
        res = pivot_wayback_campaign(
            campaign_id=campaign,
            domains=domains,
            match_mime=target.wayback_pivot.match_mime
        )
        new_findings.extend(res)

    if new_findings:
        _write_findings(new_findings)
        console.print(f"[green]Saved {len(new_findings)} pivot findings.[/green]")
    else:
        console.print("[yellow]No new pivot findings generated.[/yellow]")


@app.command()
def report(
    cluster: bool = typer.Option(False, "--cluster", help="Enable infrastructure clustering via NetworkX"),
):
    """Stage C: Generate reports."""
    findings = _read_findings()
    if not findings:
        console.print("[yellow]No findings to report.[/yellow]")
        raise typer.Exit(0)

    console.print("[bold blue]Merging domain findings and calculating confidence tiers...[/bold blue]")
    merged = merge_findings(findings)

    edges = None
    if cluster:
        console.print("[bold blue]Extracting infrastructure clusters...[/bold blue]")
        merged = generate_clusters(merged)
        edges = generate_edge_list(merged)

    generate_reports(merged, edge_list=edges)


@app.command()
def run(
    campaign: str = typer.Option(..., help="Campaign ID"),
    file: Optional[Path] = typer.Option(None, help="Path to PublicWWW CSV"),
    wayback: bool = typer.Option(False, "--wayback", help="Enable CDX pivot"),
    cluster: bool = typer.Option(False, "--cluster", help="Enable clustering in reports"),
    force_stale: bool = typer.Option(False, "--i-know-this-is-stale"),
):
    """Run full pipeline: Ingest -> Pivot -> Report."""
    console.print(f"[bold green]Starting full pipeline for {campaign}...[/bold green]")
    if file:
        ingest(campaign=campaign, file=file, force_stale=force_stale)
    
    pivot(campaign=campaign, urlscan=True, virustotal=True, wayback=wayback, force_stale=force_stale)
    report(cluster=cluster)


if __name__ == "__main__":
    app()
