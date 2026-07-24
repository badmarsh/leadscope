import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from wp_hunter.schema import Campaign

console = Console()


def generate_reports(
    merged_findings: List[Dict],
    campaigns: List[Campaign],
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate CSV, Markdown, and JSON reports from merged findings."""
    if output_dir is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        output_dir = Path("output") / timestamp

    output_dir.mkdir(parents=True, exist_ok=True)

    campaign_map = {c.id: c for c in campaigns}

    # 1. Generate report.csv
    csv_file = output_dir / "report.csv"
    fieldnames = [
        "domain",
        "campaign_id",
        "campaign_name",
        "family",
        "confidence",
        "publicwww_visible",
        "publicwww_rank",
        "in_urlscan",
        "urlscan_scan_id",
        "screenshot_url",
        "in_vt",
        "first_seen",
        "last_seen",
    ]

    with csv_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in merged_findings:
            cid = item.get("campaign_id")
            camp = campaign_map.get(cid)
            scans = item.get("urlscan_scans", [])
            primary_scan = scans[0] if scans else {}

            writer.writerow({
                "domain": item.get("domain"),
                "campaign_id": cid,
                "campaign_name": camp.name if camp else cid,
                "family": camp.family if camp else "",
                "confidence": item.get("confidence"),
                "publicwww_visible": item.get("publicwww_visible"),
                "publicwww_rank": item.get("publicwww_rank"),
                "in_urlscan": item.get("in_urlscan"),
                "urlscan_scan_id": primary_scan.get("scan_id"),
                "screenshot_url": primary_scan.get("screenshot_url"),
                "in_vt": item.get("in_vt"),
                "first_seen": item.get("first_seen"),
                "last_seen": item.get("last_seen"),
            })

    # 2. Generate report.json
    json_file = output_dir / "report.json"
    with json_file.open("w", encoding="utf-8") as f:
        json.dump(merged_findings, f, indent=2)

    # 3. Generate report.md
    md_file = output_dir / "report.md"
    
    # Group findings by campaign_id
    by_campaign: Dict[str, List[Dict]] = {}
    for item in merged_findings:
        cid = item.get("campaign_id", "unknown")
        by_campaign.setdefault(cid, []).append(item)

    with md_file.open("w", encoding="utf-8") as f:
        f.write("# WordPress Compromise Hunting Pipeline — Summary Report\n\n")
        f.write(f"*Generated at: {datetime.now(timezone.utc).isoformat()}*\n\n")

        for cid, items in by_campaign.items():
            camp = campaign_map.get(cid)
            f.write(f"## Campaign: {camp.name if camp else cid} (`{cid}`)\n\n")

            if camp:
                if camp.is_stale:
                    f.write(
                        f"> ⚠️ **WARNING: THIS CAMPAIGN IS STALE!**\n"
                        f"> Added: `{camp.added}` | Stale Threshold: `{camp.stale_after_days} days` "
                        f"(Age: {camp.days_old} days). Indicators may be expired.\n\n"
                    )

                f.write(f"- **Malware Family:** {camp.family}\n")
                f.write(f"- **Source Reference:** [{camp.source_url}]({camp.source_url})\n")
                f.write(f"- **Location Type:** `{camp.location}`\n")
                if camp.notes:
                    f.write(f"- **Notes:** {camp.notes}\n")
                f.write("\n")

            # Confidence Tier Stats
            high_rank = sum(1 for i in items if i.get("confidence") == "confirmed_high_rank")
            long_tail = sum(1 for i in items if i.get("confidence") == "confirmed_long_tail")
            pwww_only = sum(1 for i in items if i.get("confidence") == "publicwww_only")
            redacted = sum(1 for i in items if i.get("confidence") == "redacted_only")

            f.write("### Findings Summary by Confidence Tier\n\n")
            f.write("| Confidence Tier | Count | Description |\n")
            f.write("| --- | --- | --- |\n")
            f.write(f"| `confirmed_high_rank` | **{high_rank}** | Corroborated in PublicWWW (visible) and urlscan/VT |\n")
            f.write(f"| `confirmed_long_tail` | **{long_tail}** | Discovered via urlscan/VT pivots (bypasses PublicWWW rank cutoff) |\n")
            f.write(f"| `publicwww_only` | **{pwww_only}** | Visible in PublicWWW, pending pivot corroboration |\n")
            f.write(f"| `redacted_only` | **{redacted}** | Masked in PublicWWW, not yet corroborated |\n\n")


            # Detailed Findings Table
            f.write("### Discovered Sites & Evidence\n\n")
            f.write("| Domain | Confidence | PublicWWW Visible | urlscan Scan ID | Screenshot |\n")
            f.write("| --- | --- | --- | --- | --- |\n")

            for item in items:
                dom = item.get("domain")
                conf = item.get("confidence")
                p_vis = "Yes" if item.get("publicwww_visible") else "No"
                scans = item.get("urlscan_scans", [])

                if scans:
                    scan_links = ", ".join(f"[{s['scan_id']}](https://urlscan.io/result/{s['scan_id']}/)" for s in scans[:3])
                    screenshot_link = f"[Screenshot]({scans[0]['screenshot_url']})" if scans[0].get("screenshot_url") else "-"
                else:
                    scan_links = "-"
                    screenshot_link = "-"

                f.write(f"| `{dom}` | `{conf}` | {p_vis} | {scan_links} | {screenshot_link} |\n")

            f.write("\n---\n\n")

    console.print(f"[bold green]Generated reports in directory:[/bold green] {output_dir}")
    console.print(f"  - {csv_file}")
    console.print(f"  - {md_file}")
    console.print(f"  - {json_file}")

    return output_dir
