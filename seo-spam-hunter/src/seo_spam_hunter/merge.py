from collections import defaultdict
from typing import Dict, List, Optional


def merge_findings(findings: List[Dict]) -> List[Dict]:
    """Merge findings from all sources by (domain, campaign_id)."""
    merged: Dict[str, Dict] = defaultdict(
        lambda: {
            "domain": "",
            "campaign_id": "",
            "sources": set(),
            "rank": None,
            "visible": True,
            "urlscan_ips": set(),
            "urlscan_asns": set(),
            "urlscan_domhashes": set(),
            "vt_malicious": 0,
            "wayback_infection_date": None,
            "in_abusech": False,
            "abusech_records": [],
            "tier": "unknown",
        }
    )

    abusech_sources = {"urlhaus", "threatfox", "certstream"}

    for f in findings:
        domain = f.get("domain")
        cid = f.get("campaign_id")
        if not domain or not cid:
            continue

        key = f"{domain}|{cid}"
        entry = merged[key]
        entry["domain"] = domain
        entry["campaign_id"] = cid

        src = f.get("source")
        if src:
            entry["sources"].add(src)

        if src == "publicwww":
            if f.get("rank"):
                entry["rank"] = f["rank"]
            if not f.get("visible", True):
                entry["visible"] = False

        if src == "urlscan":
            if f.get("ip"):
                entry["urlscan_ips"].add(f["ip"])
            if f.get("asn"):
                entry["urlscan_asns"].add(str(f["asn"]))
            if f.get("domHash"):
                entry["urlscan_domhashes"].add(f["domHash"])

        if src in ("virustotal", "virustotal_contacted_domain", "virustotal_graph"):
            entry["vt_malicious"] = max(entry["vt_malicious"], f.get("malicious", 0))

        if src == "wayback":
            if f.get("infection_approx_date"):
                entry["wayback_infection_date"] = f["infection_approx_date"]

        if src in abusech_sources:
            entry["in_abusech"] = True
            entry["abusech_records"].append({
                "source": src,
                "threat": f.get("threat") or f.get("threatfox_malware_printable") or f.get("ct_pattern"),
                "url": f.get("url"),
            })

    # Calculate confidence tiers
    results = []
    for m in merged.values():
        sources = m["sources"]
        visible = m["visible"]

        in_p = "publicwww" in sources
        p_vis = visible
        in_pivot = any(s in ("urlscan", "virustotal", "virustotal_contacted_domain", "virustotal_graph", "wayback") for s in sources)
        in_abusech = m["in_abusech"]

        if in_p and p_vis and in_pivot:
            confidence = "confirmed_high_rank"
        elif in_pivot and (not in_p or not p_vis):
            confidence = "confirmed_long_tail"
        elif in_abusech and not in_p and not in_pivot:
            confidence = "abusech_candidate"
        elif in_p and not p_vis and not in_pivot and not in_abusech:
            confidence = "redacted_only"
        elif in_p and p_vis and not in_pivot and not in_abusech:
            confidence = "publicwww_only"
        else:
            confidence = "confirmed_long_tail"

        m["tier"] = confidence
        m["confidence"] = confidence

        # Convert sets to lists for JSON serialization
        m["sources"] = list(m["sources"])
        m["urlscan_ips"] = list(m["urlscan_ips"])
        m["urlscan_asns"] = list(m["urlscan_asns"])
        m["urlscan_domhashes"] = list(m["urlscan_domhashes"])
        
        results.append(m)

    return results
