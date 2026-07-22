import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import MagicMock, patch
import crawler_client

def test_crawler_scrape_returns_none_on_crawler_failure():
    """When crawler service returns success=False, crawler_scrape should return (None, None)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": False, "error": "Anti-bot protection"}
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp):
        md, imgs = crawler_client.crawler_scrape("https://example.com")
        assert md is None
        assert imgs is None

def test_crawler_scrape_returns_none_on_http_error():
    """When crawler service HTTP request fails, crawler_scrape should return (None, None) gracefully."""
    with patch("requests.post", side_effect=Exception("Connection refused")):
        md, imgs = crawler_client.crawler_scrape("https://example.com")
        assert md is None
        assert imgs is None
