"""
services/stages/tests/test_stage4.py
Unit tests for Stage 4 (Contact Discovery & Verification).
"""
from unittest.mock import patch, MagicMock
from services.stages.stage4 import (
    _role_priority,
    _prioritize_contacts,
    _apollo_search,
    _hunter_search,
    _hunter_verify,
    _whois_search,
    _discover_contacts,
)


def test_role_priority_ordering():
    ceo = {"role": "Chief Executive Officer", "email": "john@corp.com"}
    generic = {"role": "", "email": "info@corp.com"}
    named = {"role": "Engineer", "email": "alice@corp.com"}

    assert _role_priority(ceo) == 0
    assert _role_priority(named) == 10
    assert _role_priority(generic) == 20

    sorted_list = _prioritize_contacts([generic, ceo, named])
    assert sorted_list == [ceo, named, generic]


@patch("services.stages.stage4.requests.post")
def test_apollo_search_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "people": [
            {
                "email": "ceo@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "title": "CEO",
                "linkedin_url": "https://linkedin.com/in/janedoe",
            }
        ]
    }
    mock_post.return_value = mock_resp

    with patch("services.common.config.APOLLO_API_KEY", "test-key"):
        res = _apollo_search("example.com")
        assert len(res) == 1
        assert res[0]["email"] == "ceo@example.com"
        assert res[0]["name"] == "Jane Doe"
        assert res[0]["source"] == "apollo"


@patch("services.stages.stage4.requests.get")
def test_hunter_search_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "data": {
            "emails": [
                {
                    "value": "cto@example.com",
                    "first_name": "Bob",
                    "last_name": "Smith",
                    "position": "CTO",
                    "confidence": 90,
                }
            ]
        }
    }
    mock_get.return_value = mock_resp

    with patch("services.common.config.HUNTER_API_KEY", "test-key"):
        res = _hunter_search("example.com")
        assert len(res) == 1
        assert res[0]["email"] == "cto@example.com"
        assert res[0]["source"] == "hunter"


@patch("services.stages.stage4.requests.get")
def test_hunter_verify_statuses(mock_get):
    with patch("services.common.config.HUNTER_API_KEY", "test-key"), patch("services.common.config.HUNTER_VERIFY_CONTACTS", True):
        # Deliverable
        resp1 = MagicMock()
        resp1.raise_for_status.return_value = None
        resp1.json.return_value = {"data": {"status": "deliverable"}}
        mock_get.return_value = resp1
        assert _hunter_verify("valid@test.com") is True

        # Undeliverable
        resp2 = MagicMock()
        resp2.raise_for_status.return_value = None
        resp2.json.return_value = {"data": {"status": "undeliverable"}}
        mock_get.return_value = resp2
        assert _hunter_verify("invalid@test.com") is False

        # Risky / Unknown
        resp3 = MagicMock()
        resp3.raise_for_status.return_value = None
        resp3.json.return_value = {"data": {"status": "risky"}}
        mock_get.return_value = resp3
        assert _hunter_verify("risky@test.com") is None


@patch("services.stages.stage4.whois.whois")
def test_whois_search_success(mock_whois):
    w_mock = MagicMock()
    w_mock.emails = ["admin@example.com", "abuse@example.com"]
    w_mock.name = "Domain Registrar"
    mock_whois.return_value = w_mock

    res = _whois_search("example.com")
    assert len(res) == 1
    assert res[0]["email"] == "admin@example.com"
    assert res[0]["source"] == "whois"


@patch("services.stages.stage4.db")
@patch("services.stages.stage4._async_discover")
def test_discover_contacts_upserts(mock_async, mock_db):
    mock_async.return_value = [
        {"email": "boss@target.com", "name": "The Boss", "role": "CEO", "source": "apollo", "confidence": 90}
    ]
    mock_conn = MagicMock()

    cand = {"id": 42, "domain": "target.com"}
    res = _discover_contacts(cand, mock_conn)

    assert res["candidate_id"] == 42
    assert res["contacts_found"] == 1
    mock_db.execute.assert_called_once()
