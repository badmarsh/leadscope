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

import importlib.util
spec = importlib.util.spec_from_file_location("crawler_main", os.path.join(CRAWLER_DIR, "main.py"))
crawler_main = importlib.util.module_from_spec(spec)
sys.modules["main"] = crawler_main
spec.loader.exec_module(crawler_main)

main = crawler_main
app = crawler_main.app
CrawlRequest = crawler_main.CrawlRequest
_is_spa_likely = crawler_main._is_spa_likely

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

@patch("requests.get")
@patch("main.trafilatura")
def test_trafilatura_scrape_success(mock_trafilatura, mock_requests_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>Some text</html>"
    mock_requests_get.return_value = mock_resp
    mock_trafilatura.extract.return_value = "Some text"
    
    with patch("main._is_spa_likely", return_value=False):
        res = main._trafilatura_scrape("https://example.com")
        assert res == "Some text"
        mock_requests_get.assert_called_once_with("https://example.com", timeout=15, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

@patch("requests.get")
@patch("main.trafilatura")
def test_trafilatura_scrape_spa_detection(mock_trafilatura, mock_requests_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<script></script>" * 10
    mock_requests_get.return_value = mock_resp
    
    with patch("main._is_spa_likely", return_value=True):
        res = main._trafilatura_scrape("https://example.com")
        assert res is None  # Should return None if SPA detected

def test_health_endpoint():
    # Health endpoint always returns browser_ready=True (per-request instantiation)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["browser_ready"] is True

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

    mock_crawler_res = MagicMock()
    mock_crawler_res.success = True
    mock_crawler_res.markdown = "Playwright Markdown"
    mock_crawler_res.media = {"images": []}
    mock_crawler_res.links = {"internal": []}
    mock_crawler_res.error_message = None
    mock_crawler_res.html = ""

    mock_arun = AsyncMock(return_value=mock_crawler_res)
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.arun = mock_arun
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("main.AsyncWebCrawler", return_value=mock_crawler_instance):
        response = client.post(
            "/crawl",
            json={"url": "https://example.com"}
        )

    assert response.status_code == 200
    assert response.json()["renderer"] == "playwright"
    assert response.json()["markdown"] == "Playwright Markdown"

@patch("main._trafilatura_scrape")
@patch("httpx.AsyncClient")
def test_crawl_endpoint_image_extraction(mock_httpx_class, mock_trafilatura):
    mock_trafilatura.return_value = None  # Force Playwright path

    mock_crawler_res = MagicMock()
    mock_crawler_res.success = True
    mock_crawler_res.markdown = "Playwright Markdown with images"
    mock_crawler_res.media = {"images": []}
    mock_crawler_res.links = {"internal": []}
    mock_crawler_res.error_message = None
    mock_crawler_res.html = ""

    mock_arun = AsyncMock(return_value=mock_crawler_res)
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.arun = mock_arun
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.__aexit__ = AsyncMock(return_value=False)

    # Setup httpx mock for gemini proxy call
    mock_httpx = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"urls": ["1.jpg"]}'}}]
    }
    mock_httpx.post.return_value = mock_resp
    mock_httpx_class.return_value.__aenter__.return_value = mock_httpx

    with patch("main.AsyncWebCrawler", return_value=mock_crawler_instance):
        response = client.post(
            "/crawl",
            json={"url": "https://example.com", "extract_images": True}
        )

    assert response.status_code == 200
    assert response.json()["renderer"] == "playwright"
    assert response.json()["extracted_data"] == {"urls": ["1.jpg"]}
    mock_httpx.post.assert_called_once()
