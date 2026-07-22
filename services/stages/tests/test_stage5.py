import os
import sys
import pytest
from unittest.mock import patch, MagicMock

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

# Mock extruct before importing stage5
mock_extruct = MagicMock()
sys.modules["extruct"] = mock_extruct
mock_w3lib = MagicMock()
sys.modules["w3lib"] = mock_w3lib
sys.modules["w3lib.html"] = mock_w3lib

import stage5

@pytest.fixture
def mock_db():
    with patch("stage5.db") as m:
        m.get_conn.return_value.__enter__.return_value = MagicMock()
        m.check_stop_signal.return_value = False
        yield m

@patch("stage5.requests.get")
@patch("w3lib.html.get_base_url", return_value="https://example.com", create=True)
def test_extract_structured_data(mock_get_base_url, mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html></html>"
    mock_resp.url = "https://example.com"
    mock_get.return_value = mock_resp
    
    mock_extruct.extract.return_value = {
        "json-ld": [
            {
                "@type": "Organization",
                "name": "Test Org",
                "email": "test@test.com",
                "telephone": "+123456789"
            }
        ]
    }
    
    res = stage5._extract_structured_data("example.com")
    assert res["name"] == "Test Org"
    assert res["email"] == "test@test.com"

@patch.object(stage5.llm, "chat_json")
def test_enrich_info(mock_chat_json, mock_db):
    mock_chat_json.return_value = ({"report": "Test", "email": "a@b.com"}, 10, 20)
    
    res = stage5._enrich_info("example.com", "Test Corp", "Offer", "page text", {})
    assert res["report"] == "Test"
    assert res["email"] == "a@b.com"

@patch.object(stage5, "_scrape_domain")
@patch.object(stage5, "_extract_structured_data")
@patch.object(stage5, "_enrich_info")
def test_enrich_candidate_success(mock_enrich_info, mock_extruct, mock_scrape, mock_db):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    candidate = {
        "id": 1, "domain": "example.com", "campaign_id": 10,
        "company_name": "Test", "status": "pending_review",
        "enrichment_attempt_count": 0, "enrichment_attempted_at": None
    }
    
    # First fetchone is DNC check (return None to pass)
    # Inside _enrich_candidate it doesn't query cooldown if attempted_at is None
    mock_db.fetchone.return_value = None
    
    mock_scrape.return_value = ("Page text", "https://example.com", ["img.jpg"])
    mock_extruct.return_value = {"email": "hello@example.com"}
    mock_enrich_info.return_value = {"report": "Hello"}
    
    res = stage5._enrich_candidate(candidate, {}, conn)
    assert res["outcome"] == "enriched"
    
    # Verify the attempt count was incremented and the candidate was enriched
    assert mock_db.execute.call_count >= 2

def test_enrich_candidate_dnc(mock_db):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    candidate = {"id": 1, "domain": "example.com", "campaign_id": 10, "enrichment_attempt_count": 0}
    
    # DNC query returns a row
    mock_db.fetchone.return_value = {"1": 1}
    
    res = stage5._enrich_candidate(candidate, {}, conn)
    assert res["outcome"] == "skipped_dnc"

@patch.object(stage5, "_scrape_domain")
def test_enrich_candidate_scrape_failed(mock_scrape, mock_db):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    candidate = {
        "id": 1, "domain": "example.com", "campaign_id": 10, 
        "enrichment_attempt_count": 0, "enrichment_attempted_at": None
    }
    
    mock_db.fetchone.return_value = None  # DNC pass
    mock_scrape.return_value = (None, "", None)  # Scrape fails
    
    res = stage5._enrich_candidate(candidate, {}, conn)
    assert res["outcome"] == "crawler_failed_retry"
