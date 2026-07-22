import pytest
from unittest.mock import MagicMock, patch
import stage5

def test_code_exception_does_not_increment_attempt_count():
    """Verify that a Python code exception during enrichment does not increment enrichment_attempt_count."""
    candidate = {
        "id": 9999,
        "domain": "test-exception-domain.com",
        "campaign_id": 1,
        "enrichment_attempted_at": None,
        "enrichment_attempt_count": 0,
        "company_name": "Test Co",
    }
    campaign = {"id": 1, "business_brief": "Test brief", "slug": "test-slug", "settings": {}}
    conn = MagicMock()

    # Mock _extract_structured_data to raise an unexpected Exception
    with patch("stage5._extract_structured_data", side_effect=RuntimeError("Database query syntax error")):
        with pytest.raises(RuntimeError):
            stage5._enrich_candidate(candidate, campaign, conn)

    # Verify db.execute was NOT called to update candidates attempt_count
    # In fixed stage5, update only happens post-crawl failure or post-success
    executed_sqls = [call[0][1] for call in conn.execute.call_args_list if len(call[0]) > 1]
    attempt_increment_calls = [sql for sql in executed_sqls if "SET enrichment_attempted_at  = now()" in sql]
    assert len(attempt_increment_calls) == 0
