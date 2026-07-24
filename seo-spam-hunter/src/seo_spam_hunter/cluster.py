from typing import Dict, List
import networkx as nx
from rich.console import Console

console = Console()


def generate_clusters(merged_findings: List[Dict]) -> List[Dict]:
    """
    Build a graph from merged findings and extract connected components
    to identify attacker infrastructure clusters.
    """
    G = nx.Graph()

    for f in merged_findings:
        domain_node = f"domain:{f['domain']}"
        G.add_node(domain_node, type="domain", label=f['domain'])

        for ip in f.get("urlscan_ips", []):
            ip_node = f"ip:{ip}"
            G.add_node(ip_node, type="ip", label=ip)
            G.add_edge(domain_node, ip_node, relation="resolves_to")

        for asn in f.get("urlscan_asns", []):
            asn_node = f"asn:{asn}"
            G.add_node(asn_node, type="asn", label=asn)
            G.add_edge(domain_node, asn_node, relation="hosted_on")

        for domhash in f.get("urlscan_domhashes", []):
            dh_node = f"domhash:{domhash}"
            G.add_node(dh_node, type="domhash", label=domhash)
            G.add_edge(domain_node, dh_node, relation="has_domhash")

    # Extract connected components
    components = list(nx.connected_components(G))
    
    # Assign cluster_id to each finding based on its domain node's component
    domain_to_cluster = {}
    for idx, comp in enumerate(components):
        cluster_id = f"Cluster-{idx + 1}"
        for node in comp:
            if node.startswith("domain:"):
                domain = node.split(":", 1)[1]
                domain_to_cluster[domain] = cluster_id

    # Update findings with cluster_id
    for f in merged_findings:
        f["cluster_id"] = domain_to_cluster.get(f["domain"], "Unknown")

    console.print(f"[green]Generated {len(components)} infrastructure clusters across {len(merged_findings)} domains.[/green]")
    
    return merged_findings


def generate_edge_list(merged_findings: List[Dict]) -> List[Dict]:
    """Generate a flat edge list suitable for Maltego/Gephi import."""
    edges = []
    for f in merged_findings:
        domain = f["domain"]
        for ip in f.get("urlscan_ips", []):
            edges.append({"Source": domain, "Target": ip, "Type": "Resolves_To"})
        for asn in f.get("urlscan_asns", []):
            edges.append({"Source": domain, "Target": asn, "Type": "Hosted_On_ASN"})
        for domhash in f.get("urlscan_domhashes", []):
            edges.append({"Source": domain, "Target": domhash, "Type": "Has_DomHash"})
    return edges
