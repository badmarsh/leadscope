import os
import sys
import pytest
from bs4 import BeautifulSoup

EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

from firecrawl_client import extract_product_grid_images

def test_extract_product_grid_images_filters_garbage():
    html = """
    <html>
      <body>
        <div class="header">
          <a href="/"><img src="logo.png" alt="Company Logo" class="w-10"></a>
        </div>
        <div class="product-grid">
          <a href="/product/123">
            <img src="https://example.com/shoe1.jpg" alt="Running Shoe" width="500" height="500">
          </a>
          <a href="/product/456">
            <img src="https://example.com/shoe2.jpg" alt="Basketball Shoe" class="product-image">
          </a>
        </div>
        <div class="footer">
          <a href="https://facebook.com"><img src="fb-icon.svg" alt="Facebook"></a>
          <img src="payment-methods.jpg" alt="We accept Visa, Mastercard" width="800" height="50">
        </div>
      </body>
    </html>
    """
    
    images = extract_product_grid_images(html)
    
    # It should only extract shoe1 and shoe2
    # The logo, fb-icon, and payment-methods images should be excluded because they aren't inside
    # an <a> tag pointing to an internal product page or their aspect ratio/size screams "banner"
    
    assert len(images) == 2
    assert "https://example.com/shoe1.jpg" in images
    assert "https://example.com/shoe2.jpg" in images
    assert "logo.png" not in images
    assert "fb-icon.svg" not in images
    assert "payment-methods.jpg" not in images

def test_extract_product_grid_images_empty_html():
    images = extract_product_grid_images("")
    assert len(images) == 0

def test_extract_product_grid_images_no_links():
    html = """
    <html>
      <body>
        <img src="shoe.jpg" alt="A shoe">
      </body>
    </html>
    """
    # If the image is not inside an anchor tag, it shouldn't be extracted in grid scraping mode.
    images = extract_product_grid_images(html)
    assert len(images) == 0

from unittest.mock import patch, MagicMock
from firecrawl_client import scrape_url, scrape_domain_pages, extract_product_grid_images_via_crawler

@patch("firecrawl_client.requests.post")
def test_scrape_url_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"markdown": "Test Markdown", "html": "<p>Test</p>"}}
    mock_post.return_value = mock_resp
    
    # Test markdown only
    res = scrape_url("https://example.com")
    assert res == "Test Markdown"
    
    # Test include_html
    res_html = scrape_url("https://example.com", include_html=True)
    assert res_html == {"markdown": "Test Markdown", "html": "<p>Test</p>"}

@patch("firecrawl_client.requests.post")
def test_scrape_url_failure(mock_post):
    mock_post.side_effect = Exception("Network Error")
    res = scrape_url("https://example.com")
    assert res is None

@patch("firecrawl_client.scrape_url")
def test_scrape_domain_pages(mock_scrape_url):
    mock_scrape_url.side_effect = [
        "Home Markdown",
        "Products Markdown",
        None  # Simulate failure on third
    ]
    
    res = scrape_domain_pages("example.com", paths=["", "/products", "/about"])
    assert len(res) == 2
    assert res["https://example.com"] == "Home Markdown"
    assert res["https://example.com/products"] == "Products Markdown"

@patch("firecrawl_client.scrape_url")
def test_scrape_domain_pages_aborts_on_home_failure(mock_scrape_url):
    mock_scrape_url.return_value = None  # Home fails
    
    res = scrape_domain_pages("example.com", paths=["", "/products", "/about"])
    assert len(res) == 0
    assert mock_scrape_url.call_count == 1  # Should abort early

@patch("firecrawl_client.requests.post")
def test_extract_product_grid_images_via_crawler(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "extracted_data": {"urls": ["https://example.com/1.jpg", "/2.jpg"]}
    }
    mock_post.return_value = mock_resp
    
    res = extract_product_grid_images_via_crawler("https://example.com")
    assert len(res) == 2
    assert res[0] == "https://example.com/1.jpg"
    assert res[1] == "https:/2.jpg"

@patch("firecrawl_client.requests.post")
def test_extract_product_grid_images_via_crawler_failure(mock_post):
    mock_post.side_effect = Exception("Crawler Error")
    res = extract_product_grid_images_via_crawler("https://example.com")
    assert res == []
