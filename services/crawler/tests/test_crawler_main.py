import os
import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

CRAWLER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

mock_crawl4ai = MagicMock()
sys.modules["crawl4ai"] = mock_crawl4ai

mock_trafilatura = MagicMock()
sys.modules["trafilatura"] = mock_trafilatura

import main
from main import app, CrawlRequest, _is_spa_likely

client = TestClient(app)

def test_is_spa_likely():
    # Empty HTML
    assert _is_spa_likely("") is True
    
    # Heavy scripts, little text
    spa_html = "<script></script>" * 10 + "hello"
    assert _is_spa_likely(spa_html) is True
    
    # Normal content page
    normal_html = "<html><body>" + "This is a normal paragraph with enough text so density is high." * 500 + "</body></html>"
    assert _is_spa_likely(normal_html) is False

@patch("main.trafilatura")
def test_trafilatura_scrape_success(mock_trafilatura):
    mock_trafilatura.fetch_url.return_value = "<html>Some text</html>"
    mock_trafilatura.extract.return_value = "Some text"
    
    with patch("main._is_spa_likely", return_value=False):
        res = main._trafilatura_scrape("https://example.com")
        assert res == "Some text"

@patch("main.trafilatura")
def test_trafilatura_scrape_spa_detection(mock_trafilatura):
    mock_trafilatura.fetch_url.return_value = "<script></script>" * 10
    
    with patch("main._is_spa_likely", return_value=True):
        res = main._trafilatura_scrape("https://example.com")
        assert res is None  # Should return None if SPA detected

def test_health_endpoint():
    # Before browser init
    main._crawler = None
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["browser_ready"] is False
    
    # After browser init
    main._crawler = MagicMock()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["browser_ready"] is True

@patch("main._trafilatura_scrape")
def test_crawl_endpoint_fast_path(mock_trafilatura):
    mock_trafilatura.return_value = "Mocked Markdown " * 100  # length > 500
    
    response = client.post(
        "/crawl",
        json={"url": "https://example.com"}
    )
    
    assert response.status_code == 200
    assert response.json()["renderer"] == "trafilatura"
    assert response.json()["markdown"].startswith("Mocked Markdown")
    mock_trafilatura.assert_called_once()

@patch("main._trafilatura_scrape")
def test_crawl_endpoint_playwright_fallback(mock_trafilatura):
    mock_trafilatura.return_value = None  # Force fallback
    
    mock_crawler = AsyncMock()
    mock_crawler_res = MagicMock()
    mock_crawler_res.success = True
    mock_crawler_res.markdown = "Playwright Markdown"
    mock_crawler_res.media = {"images": []}
    mock_crawler_res.links = {"internal": []}
    mock_crawler.arun.return_value = mock_crawler_res
    main._crawler = mock_crawler
    
    response = client.post(
        "/crawl",
        json={"url": "https://example.com"}
    )
    
    assert response.status_code == 200
    assert response.json()["renderer"] == "playwright"
    assert response.json()["markdown"] == "Playwright Markdown"
    mock_crawler.arun.assert_called_once()

@patch("main._trafilatura_scrape")
@patch("httpx.AsyncClient")
def test_crawl_endpoint_image_extraction(mock_httpx_class, mock_trafilatura):
    # Setup crawler mock
    mock_crawler = AsyncMock()
    mock_crawler_res = MagicMock()
    mock_crawler_res.success = True
    mock_crawler_res.markdown = "Playwright Markdown with images"
    mock_crawler_res.media = {"images": []}
    mock_crawler_res.links = {"internal": []}
    mock_crawler.arun.return_value = mock_crawler_res
    main._crawler = mock_crawler
    
    # Setup httpx mock for gemini proxy call
    mock_httpx = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"urls": ["1.jpg"]}'}}]
    }
    mock_httpx.post.return_value = mock_resp
    mock_httpx_class.return_value.__aenter__.return_value = mock_httpx
    
    response = client.post(
        "/crawl",
        json={"url": "https://example.com", "extract_images": True}
    )
    
    assert response.status_code == 200
    assert response.json()["renderer"] == "playwright"
    assert response.json()["extracted_data"] == {"urls": ["1.jpg"]}
    mock_httpx.post.assert_called_once()
