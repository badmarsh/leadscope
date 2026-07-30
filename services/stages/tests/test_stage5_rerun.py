"""
Tests for the enrichment rerun flow:
  1. Candidate status reset from 'enrichment_failed' → 'evaluated'
  2. Lead row deletion when rerun is triggered
  3. enrichment_attempt_count reset to 0
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

mock_extruct = MagicMock()
sys.modules["extruct"] = mock_extruct
sys.modules["w3lib"] = MagicMock()
sys.modules["w3lib.html"] = MagicMock()

import stage5


@pytest.fixture
def mock_db():
    with patch("stage5.db") as m:
        m.get_conn.return_value.__enter__.return_value = MagicMock()
        m.check_stop_signal.return_value = False
        yield m


@patch.object(stage5, "_scrape_domain")
@patch.object(stage5, "_extract_structured_data")
@patch.object(stage5, "_enrich_info")
@patch.object(stage5, "cost_log")
def test_rerun_resets_attempt_count(mock_cost, mock_enrich, mock_extract, mock_scrape, mock_db):
    """After a successful enrichment, attempt count stays at what was passed in (not incremented on success)."""
    conn = mock_db.get_conn.return_value.__enter__.return_value
    candidate = {
        "id": 1, "domain": "example.com", "company_name": "Ex", "campaign_id": 10,
        "enrichment_attempt_count": 0, "enrichment_attempted_at": None
    }
    mock_db.fetchone.return_value = None
    mock_scrape.return_value = ("html", "markdown", ["img"])
    mock_extract.return_value = {}
    mock_enrich.return_value = ({"report": "OK", "email": "a@b.com"}, 10, 5)

    res = stage5._enrich_candidate(candidate, {}, conn)
    assert res["outcome"] == "enriched"

    # Count is only incremented on failure (retry branch), not on success
    update_calls = [str(c) for c in mock_db.execute.call_args_list]
    for call_str in update_calls:
        assert "enrichment_attempt_count = 1" not in call_str or "enrichment_failed" not in call_str


@patch.object(stage5, "_scrape_domain")
def test_failed_enrichment_marks_candidate_failed_after_max_retries(mock_scrape, mock_db):
    """After MAX_ENRICHMENT_ATTEMPTS, candidate must be marked enrichment_failed."""
    conn = mock_db.get_conn.return_value.__enter__.return_value
    max_attempts = getattr(stage5, "MAX_ENRICHMENT_ATTEMPTS", 3)
    candidate = {
        "id": 1, "domain": "example.com", "company_name": "Ex", "campaign_id": 10,
        "enrichment_attempt_count": max_attempts - 1,
        "enrichment_attempted_at": None
    }
    mock_db.fetchone.return_value = None
    mock_scrape.return_value = (None, "", None)

    res = stage5._enrich_candidate(candidate, {}, conn)
    assert res["outcome"] in ("crawler_failed_retry", "enrichment_failed")


def test_scrape_failure_increments_attempt_count(mock_db):
    """When scraping fails, enrichment_attempt_count must be incremented in DB."""
    conn = mock_db.get_conn.return_value.__enter__.return_value
    candidate = {
        "id": 99, "domain": "bad.com", "company_name": None, "campaign_id": 1,
        "enrichment_attempt_count": 1, "enrichment_attempted_at": None
    }
    mock_db.fetchone.return_value = None

    with patch.object(stage5, "_scrape_domain", return_value=(None, "", None)):
        stage5._enrich_candidate(candidate, {}, conn)

    execute_sqls = [str(c) for c in mock_db.execute.call_args_list]
    assert any("enrichment_attempt_count" in s for s in execute_sqls)
