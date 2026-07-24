from seo_spam_hunter.merge import merge_findings


def test_merge_confidence_tiers():
    findings = [
        {"domain": "test.com", "campaign_id": "c1", "source": "publicwww", "rank": 500, "visible": True},
        {"domain": "test.com", "campaign_id": "c1", "source": "urlscan"},
        {"domain": "redacted.com", "campaign_id": "c1", "source": "publicwww", "visible": False},
        {"domain": "longtail.com", "campaign_id": "c1", "source": "urlscan"},
        {"domain": "longtail.com", "campaign_id": "c1", "source": "virustotal"},
    ]

    merged = merge_findings(findings)
    assert len(merged) == 3

    t1 = next(m for m in merged if m["domain"] == "test.com")
    assert t1["tier"] == "confirmed_high_rank"
    assert "publicwww" in t1["sources"]
    assert "urlscan" in t1["sources"]

    r1 = next(m for m in merged if m["domain"] == "redacted.com")
    assert r1["tier"] == "redacted_only"

    l1 = next(m for m in merged if m["domain"] == "longtail.com")
    assert l1["tier"] == "confirmed_long_tail"
