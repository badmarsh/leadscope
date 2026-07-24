from seo_spam_hunter.cluster import generate_clusters


def test_generate_clusters():
    merged_findings = [
        {"domain": "site1.com", "urlscan_ips": ["1.1.1.1"], "urlscan_asns": ["AS123"], "urlscan_domhashes": ["hashA"]},
        {"domain": "site2.com", "urlscan_ips": ["1.1.1.1"], "urlscan_asns": ["AS999"], "urlscan_domhashes": ["hashB"]},
        {"domain": "site3.com", "urlscan_ips": ["2.2.2.2"], "urlscan_asns": ["AS999"], "urlscan_domhashes": ["hashB"]},
        {"domain": "isolated.com", "urlscan_ips": ["3.3.3.3"], "urlscan_asns": ["AS000"], "urlscan_domhashes": ["hashC"]},
    ]

    clusters = generate_clusters(merged_findings)

    # site1, site2, site3 should all be in the same cluster because:
    # site1 shares IP 1.1.1.1 with site2
    # site2 shares domHash 'hashB' with site3
    c1 = next(f for f in clusters if f["domain"] == "site1.com")["cluster_id"]
    c2 = next(f for f in clusters if f["domain"] == "site2.com")["cluster_id"]
    c3 = next(f for f in clusters if f["domain"] == "site3.com")["cluster_id"]
    ci = next(f for f in clusters if f["domain"] == "isolated.com")["cluster_id"]

    assert c1 == c2 == c3
    assert ci != c1
