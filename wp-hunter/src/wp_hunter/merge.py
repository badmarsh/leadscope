import json
from pathlib import Path
from typing import Dict, List, Optional


def load_findings_jsonl(findings_file: Path = Path("findings.jsonl")) -> List[Dict]:
    """Load findings from JSONL file if it exists."""
    if not findings_file.exists():
        return []
    records = []
    with findings_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def merge_findings(
    publicwww_findings: List[Dict],
    urlscan_findings: List[Dict],
    vt_findings: List[Dict],
    abusech_findings: Optional[List[Dict]] = None,
    campaign_id: Optional[str] = None,
) -> List[Dict]:
    """Merge findings from all sources by domain & campaign_id and assign confidence tier."""
    
    # Filter by campaign_id if specified
    if campaign_id:
        p_list = [f for f in publicwww_findings if f.get("campaign_id") == campaign_id]
        u_list = [f for f in urlscan_findings if f.get("campaign_id") == campaign_id]
        v_list = [f for f in vt_findings if f.get("campaign_id") == campaign_id]
        ab_list = [f for f in (abusech_findings or []) if f.get("campaign_id") == campaign_id]
    else:
        p_list = publicwww_findings
        u_list = urlscan_findings
        v_list = vt_findings
        ab_list = abusech_findings or []

    # Map of (domain, campaign_id) -> aggregated entry
    domain_map: Dict[tuple, Dict] = {}

    # 1. Process PublicWWW findings
    for rec in p_list:
        dom = rec.get("domain")
        cid = rec.get("campaign_id")
        if not dom or not cid:
            continue
        key = (dom, cid)
        if key not in domain_map:
            domain_map[key] = {
                "domain": dom,
                "campaign_id": cid,
                "in_publicwww": True,
                "publicwww_visible": rec.get("visible", False),
                "publicwww_rank": rec.get("rank"),
                "publicwww_snippet": rec.get("snippet"),
                "in_urlscan": False,
                "urlscan_scans": [],
                "in_vt": False,
                "vt_stats": [],
                "in_abusech": False,
                "abusech_records": [],
                "first_seen": rec.get("ingested_at"),
                "last_seen": rec.get("ingested_at"),
            }
        else:
            # Update if better rank or visibility
            entry = domain_map[key]
            entry["in_publicwww"] = True
            if rec.get("visible"):
                entry["publicwww_visible"] = True
            if rec.get("rank") and (entry["publicwww_rank"] is None or rec["rank"] < entry["publicwww_rank"]):
                entry["publicwww_rank"] = rec["rank"]

    # 2. Process urlscan findings
    for rec in u_list:
        dom = rec.get("domain")
        cid = rec.get("campaign_id")
        if not dom or not cid:
            continue
        key = (dom, cid)
        if key not in domain_map:
            domain_map[key] = {
                "domain": dom,
                "campaign_id": cid,
                "in_publicwww": False,
                "publicwww_visible": False,
                "publicwww_rank": None,
                "publicwww_snippet": None,
                "in_urlscan": True,
                "urlscan_scans": [],
                "in_vt": False,
                "vt_stats": [],
                "in_abusech": False,
                "abusech_records": [],
                "first_seen": rec.get("first_seen"),
                "last_seen": rec.get("last_seen"),
            }
        entry = domain_map[key]
        entry["in_urlscan"] = True
        if rec.get("scan_id"):
            entry["urlscan_scans"].append({
                "scan_id": rec.get("scan_id"),
                "page_url": rec.get("page_url"),
                "screenshot_url": rec.get("screenshot_url"),
            })
        if rec.get("first_seen") and (not entry["first_seen"] or rec["first_seen"] < entry["first_seen"]):
            entry["first_seen"] = rec["first_seen"]
        if rec.get("last_seen") and (not entry["last_seen"] or rec["last_seen"] > entry["last_seen"]):
            entry["last_seen"] = rec["last_seen"]

    # 3. Process VirusTotal findings
    for rec in v_list:
        dom = rec.get("domain")
        cid = rec.get("campaign_id")
        if not dom:
            continue
        key = (dom, cid)
        if key not in domain_map:
            domain_map[key] = {
                "domain": dom,
                "campaign_id": cid,
                "in_publicwww": False,
                "publicwww_visible": False,
                "publicwww_rank": None,
                "publicwww_snippet": None,
                "in_urlscan": False,
                "urlscan_scans": [],
                "in_vt": True,
                "vt_stats": [],
                "in_abusech": False,
                "abusech_records": [],
                "first_seen": None,
                "last_seen": None,
            }
        entry = domain_map[key]
        entry["in_vt"] = True
        entry["vt_stats"].append(rec)

    # 4. Process Abuse.ch findings (URLhaus / ThreatFox)
    abusech_sources = {"urlhaus", "threatfox"}
    for rec in ab_list:
        if rec.get("source") not in abusech_sources:
            continue
        dom = rec.get("domain")
        cid = rec.get("campaign_id")
        if not dom or not cid:
            continue
        key = (dom, cid)
        if key not in domain_map:
            domain_map[key] = {
                "domain": dom,
                "campaign_id": cid,
                "in_publicwww": False,
                "publicwww_visible": False,
                "publicwww_rank": None,
                "publicwww_snippet": None,
                "in_urlscan": False,
                "urlscan_scans": [],
                "in_vt": False,
                "vt_stats": [],
                "in_abusech": True,
                "abusech_records": [],
                "first_seen": rec.get("first_seen") or rec.get("ingested_at"),
                "last_seen": rec.get("ingested_at"),
            }
        entry = domain_map[key]
        entry.setdefault("in_abusech", False)
        entry.setdefault("abusech_records", [])
        entry["in_abusech"] = True
        entry["abusech_records"].append({
            "source": rec.get("source"),
            "threat": rec.get("threat") or rec.get("threatfox_malware_printable"),
            "url": rec.get("url"),
        })

    # 5. Assign confidence tiers
    merged_results = []
    for key, entry in domain_map.items():
        in_p = entry["in_publicwww"]
        p_vis = entry["publicwww_visible"]
        in_pivot = entry["in_urlscan"] or entry["in_vt"]
        in_abusech = entry.get("in_abusech", False)

        if in_p and p_vis and in_pivot:
            confidence = "confirmed_high_rank"
        elif in_pivot and (not in_p or not p_vis):
            confidence = "confirmed_long_tail"
        elif in_abusech and not in_p and not in_pivot:
            confidence = "abusech_candidate"   # NEW tier — needs active validation
        elif in_p and not p_vis and not in_pivot and not in_abusech:
            confidence = "redacted_only"
        elif in_p and p_vis and not in_pivot and not in_abusech:
            # Visible in PublicWWW but not yet corroborated by pivot sources
            confidence = "publicwww_only"
        else:
            confidence = "confirmed_long_tail"

        entry["confidence"] = confidence
        merged_results.append(entry)

    return merged_results
