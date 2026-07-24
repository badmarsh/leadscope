from wp_hunter.merge import merge_findings


def test_merge_confidence_assignment():
    publicwww = [
        {"domain": "high-rank.com", "campaign_id": "c1", "visible": True, "rank": 100, "snippet": "code"},
        {"domain": "redacted.com", "campaign_id": "c1", "visible": False, "rank": None, "snippet": "Upgrade to view"},
    ]

    urlscan = [
        {"domain": "high-rank.com", "campaign_id": "c1", "scan_id": "s1", "page_url": "https://high-rank.com", "screenshot_url": "http://img", "first_seen": "2026-01-01", "last_seen": "2026-01-01"},
        {"domain": "long-tail.org", "campaign_id": "c1", "scan_id": "s2", "page_url": "https://long-tail.org", "screenshot_url": "http://img2", "first_seen": "2026-01-02", "last_seen": "2026-01-02"},
    ]

    merged = merge_findings(publicwww, urlscan, [], campaign_id="c1")
    merged_map = {m["domain"]: m["confidence"] for m in merged}

    assert merged_map["high-rank.com"] == "confirmed_high_rank"
    assert merged_map["redacted.com"] == "redacted_only"
    assert merged_map["long-tail.org"] == "confirmed_long_tail"
