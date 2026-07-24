from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from wp_hunter.ingest import ingest_abusech, ingest_publicwww, save_findings_jsonl
from wp_hunter.merge import load_findings_jsonl, merge_findings
from wp_hunter.pivot_urlscan import pivot_urlscan_campaign
from wp_hunter.pivot_vt import pivot_vt_campaign
from wp_hunter.report import generate_reports
from wp_hunter.schema import freshness_gate, load_campaigns

app = typer.Typer(help="WordPress Compromise Hunting Pipeline — Passive OSINT Recon")
console = Console()


@app.command()
def ingest(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign ID from campaigns.yaml"),
    file: Path = typer.Option(..., "--file", "-f", help="Path to PublicWWW CSV or text paste export"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config", help="Path to campaigns.yaml"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass Stage D freshness gate"),
):
    """Stage A: Ingest PublicWWW export data into findings.jsonl."""
    campaigns = load_campaigns(config)
    camp = next((c for c in campaigns if c.id == campaign), None)
    if not camp:
        console.print(f"[bold red]Error: Campaign ID '{campaign}' not found in {config}[/bold red]")
        raise typer.Exit(code=1)

    try:
        freshness_gate([camp], force_stale=i_know_this_is_stale)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)

    if camp.fit == "not_suitable_for_publicwww" or camp.publicwww_query is None:
        console.print(
            f"[yellow]Notice: Campaign '{campaign}' has fit='not_suitable_for_publicwww' or null query. Skipping PublicWWW ingestion.[/yellow]"
        )
        return

    ingest_publicwww(campaign_id=campaign, file_path=file)


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
    )
    console.print(f"[bold green]Ingested {len(records)} Abuse.ch records for '{campaign}'.[/bold green]")


@app.command()
def pivot(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign ID from campaigns.yaml"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config", help="Path to campaigns.yaml"),
    max_pages: int = typer.Option(10, "--max-pages", help="Max urlscan search pages to query"),
    vt_pivot_domains: bool = typer.Option(False, "--vt-pivot-domains", help="Pivot contacted domains in VirusTotal"),
    vt_graph: bool = typer.Option(False, "--vt-graph", help="Enable VT graph-walk pivot on seed domains"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass Stage D freshness gate"),
):
    """Stage B: Query urlscan.io and VirusTotal APIs for pivot indicators."""
    campaigns = load_campaigns(config)
    camp = next((c for c in campaigns if c.id == campaign), None)
    if not camp:
        console.print(f"[bold red]Error: Campaign ID '{campaign}' not found in {config}[/bold red]")
        raise typer.Exit(code=1)

    try:
        freshness_gate([camp], force_stale=i_know_this_is_stale)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)

    urlscan_results = []
    if camp.urlscan_pivot:
        urlscan_results = pivot_urlscan_campaign(campaign_id=campaign, pivot_queries=camp.urlscan_pivot, max_pages=max_pages)

    vt_results = []
    if camp.virustotal_pivot and (camp.virustotal_pivot.hashes or camp.virustotal_pivot.domains):
        vt_results = pivot_vt_campaign(
            campaign_id=campaign,
            hashes=camp.virustotal_pivot.hashes,
            domains=camp.virustotal_pivot.domains,
            pivot_contacted_domains=vt_pivot_domains,
            graph_pivot=vt_graph,
        )

    all_pivot = urlscan_results + vt_results
    if all_pivot:
        save_findings_jsonl(all_pivot)

    console.print(f"[bold green]Pivot complete for '{campaign}': {len(urlscan_results)} urlscan hits, {len(vt_results)} VT hits saved to findings.jsonl.[/bold green]")


@app.command()
def report(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Optional Campaign ID to filter report"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config", help="Path to campaigns.yaml"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass Stage D freshness gate"),
):
    """Stage C: Merge findings and generate CSV, Markdown, and JSON reports."""
    campaigns = load_campaigns(config)
    if campaign:
        camp = next((c for c in campaigns if c.id == campaign), None)
        if camp:
            try:
                freshness_gate([camp], force_stale=i_know_this_is_stale)
            except ValueError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(code=1)

    all_findings = load_findings_jsonl()

    publicwww_findings = [f for f in all_findings if f.get("source") == "publicwww"]
    urlscan_findings = [f for f in all_findings if f.get("source") == "urlscan"]
    vt_findings = [f for f in all_findings if f.get("source") in ("virustotal", "virustotal_contacted_domain", "virustotal_graph")]
    abusech_findings = [f for f in all_findings if f.get("source") in ("urlhaus", "threatfox")]

    # Run merge
    merged = merge_findings(
        publicwww_findings=publicwww_findings,
        urlscan_findings=urlscan_findings,
        vt_findings=vt_findings,
        abusech_findings=abusech_findings,
        campaign_id=campaign,
    )

    if not merged:
        console.print("[yellow]No merged findings found to report. Ingest or pivot first.[/yellow]")
        return

    generate_reports(merged, campaigns)


@app.command()
def run(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign ID from campaigns.yaml"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Optional PublicWWW export file"),
    config: Path = typer.Option(Path("campaigns.yaml"), "--config", help="Path to campaigns.yaml"),
    i_know_this_is_stale: bool = typer.Option(False, "--i-know-this-is-stale", help="Bypass Stage D freshness gate for expired campaigns"),
):
    """One-shot run: Freshness gate -> Ingest -> Pivot -> Report."""
    campaigns = load_campaigns(config)
    camp = next((c for c in campaigns if c.id == campaign), None)
    if not camp:
        console.print(f"[bold red]Error: Campaign ID '{campaign}' not found in {config}[/bold red]")
        raise typer.Exit(code=1)

    # Stage D — Freshness gate
    try:
        freshness_gate([camp], force_stale=i_know_this_is_stale)
    except ValueError as e:
        console.print(f"[bold red]{e}[/bold red]")
        raise typer.Exit(code=1)

    # Stage A — Ingest
    publicwww_records = []
    if file and camp.fit != "not_suitable_for_publicwww" and camp.publicwww_query:
        publicwww_records = ingest_publicwww(campaign_id=campaign, file_path=file)
    else:
        all_jsonl = load_findings_jsonl()
        publicwww_records = [r for r in all_jsonl if r.get("campaign_id") == campaign and r.get("source") == "publicwww"]

    # Stage B — Pivot
    urlscan_records = []
    if camp.urlscan_pivot:
        urlscan_records = pivot_urlscan_campaign(campaign_id=campaign, pivot_queries=camp.urlscan_pivot)

    vt_records = []
    if camp.virustotal_pivot and (camp.virustotal_pivot.hashes or camp.virustotal_pivot.domains):
        vt_records = pivot_vt_campaign(
            campaign_id=campaign,
            hashes=camp.virustotal_pivot.hashes,
            domains=camp.virustotal_pivot.domains,
        )

    all_pivot = urlscan_records + vt_records
    if all_pivot:
        save_findings_jsonl(all_pivot)

    all_findings = load_findings_jsonl()
    abusech_findings = [f for f in all_findings if f.get("source") in ("urlhaus", "threatfox")]

    # Merge & Report
    merged = merge_findings(
        publicwww_findings=publicwww_records,
        urlscan_findings=urlscan_records,
        vt_findings=vt_records,
        abusech_findings=abusech_findings,
        campaign_id=campaign,
    )

    if merged:
        generate_reports(merged, campaigns)
    else:
        console.print("[yellow]Pipeline finished with 0 findings.[/yellow]")


if __name__ == "__main__":
    app()
