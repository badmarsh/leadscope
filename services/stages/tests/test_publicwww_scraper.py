import pytest
from unittest.mock import patch, MagicMock

import publicwww_scraper

def test_extract_domain():
    assert publicwww_scraper.extract_domain("https://www.example.com") == "example.com"
    assert publicwww_scraper.extract_domain("http://sub.example.co.uk/path?q=1") == "example.co.uk"
    assert publicwww_scraper.extract_domain("example.com") == "example.com"
    assert publicwww_scraper.extract_domain("invalid") is None

def test_parse_domains_from_markdown():
    # This simulates the markdown returned by the crawler extracting PublicWWW tables
    markdown_content = """
    | Rank | Url | Snippet |
    |---|---|---|
    | 1 | [](https://example.com/) https://example.com/ | `eval(base64_decode(` |
    | 2 | [](http://www.test-site.org/page) http://www.test-site.org/page | `eval(base64_decode(` |
    | 3 | [](https://github.com/repo) https://github.com/repo | `eval(base64_decode(` |
    | 4 | [](https://publicwww.com/search) https://publicwww.com/search | `eval(base64_decode(` |
    | 5 | [](https://example.com/other) https://example.com/other | `eval(base64_decode(` |
    """
    
    domains = publicwww_scraper.parse_domains_from_markdown(markdown_content)
    
    # Expect example.com and test-site.org. 
    # github.com and publicwww.com are in BLOCKLIST_DOMAINS. 
    # example.com/other should be deduplicated to example.com.
    assert len(domains) == 2
    assert "example.com" in domains
    assert "test-site.org" in domains
    assert "github.com" not in domains
    assert "publicwww.com" not in domains

@patch("publicwww_scraper.upsert_candidate", return_value=True)
@patch("publicwww_scraper.crawl_publicwww")
def test_scrape_signature_pagination(mock_crawl, mock_upsert, mock_env, mock_db_conn):
    # Page 1 returns 25 total results and 1 valid domain
    page1_markdown = "25 web pages in 0.12 s.\n| 1 | [](https://site1.com/) https://site1.com/ | snippet |"
    
    # Page 2 returns 1 valid domain
    page2_markdown = "| 11 | [](https://site2.com/) https://site2.com/ | snippet |"
    
    # Page 3 returns no domains, which should halt pagination
    page3_markdown = "No results"

    mock_crawl.side_effect = [page1_markdown, page2_markdown, page3_markdown]

    sig = {
        "id": 99,
        "snippet": "eval(base64(",
        "malware_family": "TestMalware",
        "confidence": "high"
    }

    # Use a small max_pages and a mock sleep to speed up test
    with patch("publicwww_scraper.time.sleep"):
        res = publicwww_scraper.scrape_signature(
            sig, 
            campaign_id=1, 
            conn=mock_db_conn, 
            dry_run=False, 
            max_pages=5
        )

    # We expect 3 calls to crawl because page 3 had no domains, stopping the loop
    assert mock_crawl.call_count == 3
    
    # We expect 2 domains found and 2 inserted
    assert res["domains_found"] == 2
    assert res["inserted"] == 2
    assert mock_upsert.call_count == 2
