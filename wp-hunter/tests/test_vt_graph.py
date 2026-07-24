"""Tests for VT graph-walk pivot."""
from unittest.mock import patch, MagicMock
from wp_hunter.pivot_vt import graph_walk_domain, RateLimiter


def _make_limiter():
    lim = RateLimiter(requests_per_minute=9999)
    return lim


def test_graph_walk_returns_sibling_domains():
    fake_hashes = ["abc123", "def456"]
    fake_siblings = ["sibling1.com", "sibling2.com"]

    with patch("wp_hunter.pivot_vt.query_vt_domain_urls", return_value=fake_hashes), \
         patch("wp_hunter.pivot_vt._fetch_contacted_domains_for_hash", return_value=fake_siblings):

        results = graph_walk_domain(
            seed_domain="evil.com",
            campaign_id="test-campaign",
            api_key="FAKE",
            limiter=_make_limiter(),
            max_hashes=5,
        )

    assert len(results) > 0
    domains = [r["domain"] for r in results]
    assert "sibling1.com" in domains
    assert "sibling2.com" in domains
    for r in results:
        assert r["source"] == "virustotal_graph"
        assert r["graph_seed"] == "evil.com"
        assert r["campaign_id"] == "test-campaign"


def test_graph_walk_deduplicates_seed():
    """Seed domain should not appear as its own sibling."""
    with patch("wp_hunter.pivot_vt.query_vt_domain_urls", return_value=["hash1"]), \
         patch("wp_hunter.pivot_vt._fetch_contacted_domains_for_hash", return_value=["evil.com", "other.com"]):

        results = graph_walk_domain(
            seed_domain="evil.com",
            campaign_id="test-campaign",
            api_key="FAKE",
            limiter=_make_limiter(),
        )

    domains = [r["domain"] for r in results]
    assert "evil.com" not in domains
    assert "other.com" in domains


def test_graph_walk_no_hashes_returns_empty():
    with patch("wp_hunter.pivot_vt.query_vt_domain_urls", return_value=[]):
        results = graph_walk_domain(
            seed_domain="clean.com",
            campaign_id="test",
            api_key="FAKE",
            limiter=_make_limiter(),
        )
    assert results == []
