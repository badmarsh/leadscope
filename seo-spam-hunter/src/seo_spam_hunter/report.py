import csv
import json
from pathlib import Path
from typing import Dict, List
from rich.console import Console

console = Console()


def write_csv(findings: List[Dict], out_path: Path):
    if not findings:
        return
    keys = ["domain", "campaign_id", "tier", "sources", "rank", "visible", "vt_malicious", "wayback_infection_date", "cluster_id"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        for row in findings:
            row_copy = row.copy()
            row_copy["sources"] = "|".join(row_copy.get("sources", []))
            writer.writerow(row_copy)


def write_json(findings: List[Dict], out_path: Path):
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)


def write_edge_list(edges: List[Dict], out_path: Path):
    if not edges:
        return
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Source", "Target", "Type"])
        writer.writeheader()
        writer.writerows(edges)


def write_markdown(findings: List[Dict], out_path: Path):
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# SEO Spam & Backdoor Findings Report\n\n")

        # Tier breakdown
        tiers = {}
        for row in findings:
            t = row.get("tier", "unknown")
            tiers[t] = tiers.get(t, 0) + 1

        f.write("## Confidence Tiers Summary\n")
        for t, count in tiers.items():
            f.write(f"- **{t}**: {count}\n")
        f.write("\n")

        # Clusters summary
        clusters = {}
        for row in findings:
            cid = row.get("cluster_id")
            if cid:
                if cid not in clusters:
                    clusters[cid] = []
                clusters[cid].append(row)
        
        if clusters:
            f.write("## Infrastructure Clusters Summary\n")
            for cid, c_findings in sorted(clusters.items()):
                f.write(f"### {cid}\n")
                f.write(f"**Size**: {len(c_findings)} domains\n\n")
                f.write("| Domain | IP | ASN | DomHash | Wayback Date |\n")
                f.write("|---|---|---|---|---|\n")
                for item in c_findings[:10]: # Top 10 per cluster to avoid massive files
                    ip = ", ".join(item.get("urlscan_ips", []))
                    asn = ", ".join(item.get("urlscan_asns", []))
                    domhash = ", ".join(item.get("urlscan_domhashes", []))
                    w_date = item.get("wayback_infection_date") or "-"
                    f.write(f"| {item['domain']} | {ip} | {asn} | {domhash} | {w_date} |\n")
                if len(c_findings) > 10:
                    f.write(f"| ... and {len(c_findings) - 10} more. |\n")
                f.write("\n")


def generate_reports(
    merged_findings: List[Dict], 
    edge_list: List[Dict] = None,
    output_dir: Path = Path("output")
):
    output_dir.mkdir(exist_ok=True)
    
    write_csv(merged_findings, output_dir / "report.csv")
    write_json(merged_findings, output_dir / "report.json")
    write_markdown(merged_findings, output_dir / "report.md")
    
    if edge_list:
        write_edge_list(edge_list, output_dir / "report_edges.csv")

    console.print(f"[green]Reports written to {output_dir.absolute()}[/green]")
