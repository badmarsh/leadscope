"""
Unit tests for stage2.py helper functions.
Uses mocked db connections — no real Postgres required.
"""
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "services/stages")


@pytest.fixture
def mock_conn():
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: self
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_is_do_not_contact_returns_true_when_domain_blocked(mock_conn):
    from stage2 import _is_do_not_contact
    with patch("stage2.db.fetchone", return_value={"1": 1}):
        assert _is_do_not_contact(mock_conn, "blocked.com", 1) is True


def test_is_do_not_contact_returns_false_when_domain_clear(mock_conn):
    from stage2 import _is_do_not_contact
    with patch("stage2.db.fetchone", return_value=None):
        assert _is_do_not_contact(mock_conn, "clear.com", 1) is False


@pytest.mark.parametrize("url,expected", [
    ("https://www.example.com/path?q=1", "example.com"),
    ("www.example.hu", "example.hu"),
    ("http://shop.example.com:8080/", "shop.example.com"),
    ("not-a-domain", None),
    ("", None),
])
def test_extract_domain(url, expected):
    from stage2 import _extract_domain
    assert _extract_domain(url) == expected


def test_upsert_candidate_skips_dnc_domain(mock_conn):
    from stage2 import _upsert_candidate
    with patch("stage2._is_do_not_contact", return_value=True):
        result = _upsert_candidate(
            mock_conn,
            campaign_id=1,
            domain="blocked.com",
            company_name=None,
            source="keyword_search",
            query_used="test",
            evidence_data={},
        )
    assert result is False


def test_upsert_candidate_returns_true_on_insert(mock_conn):
    from stage2 import _upsert_candidate
    with patch("stage2._is_do_not_contact", return_value=False), \
         patch("stage2.db.execute", return_value=1):
        result = _upsert_candidate(
            mock_conn,
            campaign_id=1,
            domain="new-lead.com",
            company_name="New Lead Ltd",
            source="keyword_search",
            query_used="test",
            evidence_data={"test": True},
        )
    assert result is True


def test_upsert_candidate_returns_false_when_no_rows_affected(mock_conn):
    from stage2 import _upsert_candidate
    with patch("stage2._is_do_not_contact", return_value=False), \
         patch("stage2.db.execute", return_value=0):
        result = _upsert_candidate(
            mock_conn,
            campaign_id=1,
            domain="existing.com",
            company_name=None,
            source="keyword_search",
            query_used="test",
            evidence_data={},
        )
    assert result is False
