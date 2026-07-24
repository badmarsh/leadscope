import pytest
from unittest.mock import patch, MagicMock
import os

import kb_ingest

# ---------------------------------------------------------------------------
# fetch_rss_items
# ---------------------------------------------------------------------------
def test_fetch_rss_items_success():
    xml_data = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>New Malware Variant</title>
                <link>https://example.com/malware</link>
            </item>
            <item>
                <title>Security Update</title>
                <link>https://example.com/update</link>
            </item>
        </channel>
    </rss>
    """
    with patch("kb_ingest.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = xml_data
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        items = kb_ingest.fetch_rss_items("https://fake.rss")
        
        assert len(items) == 2
        assert items[0]["title"] == "New Malware Variant"
        assert items[0]["url"] == "https://example.com/malware"
        assert items[1]["title"] == "Security Update"
        assert items[1]["url"] == "https://example.com/update"

def test_fetch_rss_items_failure():
    with patch("kb_ingest.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        items = kb_ingest.fetch_rss_items("https://fake.rss")
        assert items == []

# ---------------------------------------------------------------------------
# extract_article_links_from_index
# ---------------------------------------------------------------------------
def test_extract_article_links_from_index_success():
    mock_conn = MagicMock()
    with patch("kb_ingest.crawler_scrape", return_value=("Page content", [])) as mock_crawl, \
         patch("kb_ingest.llm.chat_json", return_value=(["https://example.com/article1", "https://example.com/article2"], 10, 5)) as mock_llm, \
         patch("kb_ingest.cost_log.log_call"):
        
        links = kb_ingest.extract_article_links_from_index("https://fake.index", 1, mock_conn)
        
        assert len(links) == 2
        assert links[0]["url"] == "https://example.com/article1"
        assert links[1]["url"] == "https://example.com/article2"
        mock_crawl.assert_called_once_with("https://fake.index", force_playwright=False)

def test_extract_article_links_from_index_scrape_fail():
    mock_conn = MagicMock()
    with patch("kb_ingest.crawler_scrape", return_value=(None, [])):
        links = kb_ingest.extract_article_links_from_index("https://fake.index", 1, mock_conn)
        assert links == []

# ---------------------------------------------------------------------------
# fetch_github_files
# ---------------------------------------------------------------------------
def test_fetch_github_files_success():
    github_json = {
        "tree": [
            {"type": "blob", "path": "malware.php"},
            {"type": "blob", "path": "readme.md"},
            {"type": "blob", "path": "backdoor.js"},
            {"type": "tree", "path": "folder"}
        ]
    }
    with patch("kb_ingest.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = github_json
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        items = kb_ingest.fetch_github_files("https://api.github.com/repos/user/repo/git/trees/main?recursive=1")
        
        assert len(items) == 2
        assert items[0]["url"] == "https://raw.githubusercontent.com/user/repo/HEAD/malware.php"
        assert items[1]["url"] == "https://raw.githubusercontent.com/user/repo/HEAD/backdoor.js"

# ---------------------------------------------------------------------------
# Pipeline run()
# ---------------------------------------------------------------------------
def test_run_pipeline_success(mock_env, mock_db_conn):
    # Mock campaign lookup
    def fake_fetchone(conn, sql, params=None):
        if "slug = 'wp-remediation'" in sql:
            return {"id": 1}
        if "SELECT 1 FROM kb_articles" in sql:
            return None  # Simulate article not seen before
        return None

    # Mock sources
    def fake_fetchall(conn, sql, params=None):
        if "threat_intel_sources" in sql:
            return [
                {"id": 1, "name": "RSS Source", "url": "https://rss", "type": "rss"}
            ]
        return []
    
    # Mock LLM response extracting a valid signature
    llm_output = [{
        "snippet": "eval(base64_decode(",
        "malware_family": "FakePlugin",
        "confidence": "high",
        "sneakiness_tier": "A",
        "proof_method": "Check plugin dir",
        "outreach_hook": "Found fake plugin",
        "outbreak_scope": "Global"
    }]

    with patch("kb_ingest.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("kb_ingest.db.fetchone", side_effect=fake_fetchone), \
         patch("kb_ingest.db.fetchall", side_effect=fake_fetchall), \
         patch("kb_ingest.db.execute") as mock_execute, \
         patch("kb_ingest.fetch_rss_items", return_value=[{"title": "Malware Found", "url": "https://rss/1"}]), \
         patch("kb_ingest.crawler_scrape", return_value=("This is a very long text about malware details that is definitely longer than one hundred characters so that it passes the validation check inside kb_ingest.py", [])), \
         patch("kb_ingest.llm.chat_json", return_value=(llm_output, 10, 5)), \
         patch("kb_ingest.cost_log.log_call"):
        
        stats = kb_ingest.run()
        
        assert stats["sources_checked"] == 1
        assert stats["articles_processed"] == 1
        assert stats["signatures_extracted"] == 1
        assert stats["errors"] == 0

        # Verify insertion queries
        execute_calls = mock_execute.call_args_list
        insert_sig_call = any("INSERT INTO malware_signatures" in call[0][1] for call in execute_calls)
        assert insert_sig_call is True

def test_run_pipeline_skips_non_threat_rss(mock_env, mock_db_conn):
    """RSS articles without threat keywords in the title should be skipped."""
    def fake_fetchone(conn, sql, params=None):
        if "slug = 'wp-remediation'" in sql:
            return {"id": 1}
        return None

    def fake_fetchall(conn, sql, params=None):
        return [{"id": 1, "name": "RSS", "url": "https://rss", "type": "rss"}]
    
    with patch("kb_ingest.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("kb_ingest.db.fetchone", side_effect=fake_fetchone), \
         patch("kb_ingest.db.fetchall", side_effect=fake_fetchall), \
         patch("kb_ingest.fetch_rss_items", return_value=[{"title": "Unrelated News Update", "url": "https://rss/1"}]):
        
        stats = kb_ingest.run()
        
        assert stats["articles_skipped"] == 1
        assert stats["articles_processed"] == 0
