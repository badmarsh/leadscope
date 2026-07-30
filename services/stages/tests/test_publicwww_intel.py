"""
services/stages/tests/test_publicwww_intel.py
Unit tests for PublicWWW intel query scraper and URLScan pivot.
"""
from unittest.mock import patch, MagicMock
from services.stages.publicwww_intel_scraper import extract_c2_domains, process_query, crawl_publicwww


def test_extract_c2_domains():
    markdown = """
    Check out these malicious domains:
    - https://c2-malware-server.com/payload.js
    - http://publicwww.com/websites/test
    - https://infected-host.net/admin
    """
    domains = extract_c2_domains(markdown)
    assert "c2-malware-server.com" in domains
    assert "infected-host.net" in domains
    assert "publicwww.com" not in domains


@patch("services.stages.publicwww_intel_scraper.requests.post")
def test_crawl_publicwww_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": True, "markdown": "Some markdown content"}
    mock_post.return_value = mock_resp

    md = crawl_publicwww("wordpress", "c2-pattern")
    assert md == "Some markdown content"


@patch("services.stages.publicwww_intel_scraper.time.sleep")
@patch("services.stages.publicwww_intel_scraper.fetch_urlscan_results")
@patch("services.stages.publicwww_intel_scraper.crawl_publicwww")
def test_process_query_dry_run(mock_crawl, mock_urlscan, mock_sleep):
    mock_crawl.return_value = "Found https://bad-c2.com"
    mock_urlscan.return_value = [
        {"page": {"url": "https://victim-site.com/page"}}
    ]

    mock_conn = MagicMock()
    query_row = {
        "id": 1,
        "campaign_id": 10,
        "name": "Test Query",
        "query_string": "test",
        "snipexp_regex": "regex",
        "confidence": 80,
    }

    stats = process_query(mock_conn, query_row, dry_run=True)
    assert stats["inserted"] == 1
    assert stats["pivots"] == 1
