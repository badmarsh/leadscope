"""Tests for Stage 0 CT log monitor pattern matching."""
import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock

from seo_spam_hunter.stage0_ct import _matches_any, _extract_domains_from_message, _monitor_certstream, run_ct_monitor


def test_pharma_pattern_matches():
    assert _matches_any("buy-viagra-online.com") is not None
    assert _matches_any("cheapcialispharmacy.net") is not None
    assert _matches_any("xanax-overnight.com") is not None


def test_lookalike_pattern_matches():
    assert _matches_any("paypa1-secure.com") is not None
    assert _matches_any("g00gle-verify.net") is not None


def test_clean_domain_no_match():
    assert _matches_any("mynormalwebsite.com") is None
    assert _matches_any("legitpharmaceutical.co.uk") is None   # no match on 'pharmaceutical'


def test_extract_domains_from_certstream_message():
    msg = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "*.viagra-shop.com"},
                "all_domains": ["viagra-shop.com", "www.viagra-shop.com", "mail.example.org"],
            }
        }
    }
    domains = _extract_domains_from_message(msg)
    assert "viagra-shop.com" in domains
    assert "example.org" in domains
    # Subdomains and wildcard prefixes are stripped to apex domains
    assert "*.viagra-shop.com" not in domains
    assert "www.viagra-shop.com" not in domains
    assert "mail.example.org" not in domains


def test_extract_domains_empty_message():
    assert _extract_domains_from_message({}) == []
    assert _extract_domains_from_message({"message_type": "heartbeat"}) == []


@pytest.mark.asyncio
@patch("websockets.connect")
async def test_monitor_certstream(mock_connect, tmp_path):
    mock_ws = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_ws
    
    msg = {
        "message_type": "certificate_update",
        "data": {
            "leaf_cert": {
                "subject": {"CN": "viagra.com"},
                "all_domains": ["viagra.com"]
            }
        }
    }
    mock_ws.recv.side_effect = [json.dumps(msg)]
    
    findings_file = tmp_path / "findings.jsonl"
    matched = await _monitor_certstream(
        campaign_id="test",
        findings_file=findings_file,
        max_certs=1,
        duration_seconds=None,
        feed_url="wss://test"
    )
    
    assert matched == 1
    assert findings_file.exists()

@patch("seo_spam_hunter.stage0_ct.asyncio.run")
def test_run_ct_monitor(mock_run, tmp_path):
    mock_run.return_value = 1
    res = run_ct_monitor("test", tmp_path / "f.jsonl")
    assert res == 1
