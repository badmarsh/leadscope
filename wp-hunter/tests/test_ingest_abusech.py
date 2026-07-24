"""Tests for Abuse.ch feed ingest."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from wp_hunter.ingest_abusech import fetch_urlhaus, fetch_threatfox, _extract_domain


def test_extract_domain_strips_scheme_and_path():
    assert _extract_domain("https://evil.com/malware.php") == "evil.com"
    assert _extract_domain("http://shop.evil.com:8080/wp-admin") == "shop.evil.com"
    assert _extract_domain("evil.com") == "evil.com"


def test_fetch_urlhaus_filters_wordpress_tags(tmp_path):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "query_status": "ok",
        "urls": [
            {"url": "http://wordpress-site.com/malware.php", "tags": ["wordpress", "emotet"], "id": "1", "url_status": "online", "threat": "malware_download", "date_added": "2026-01-01"},
            {"url": "http://no-wp-tag.com/file.exe", "tags": ["banking"], "id": "2", "url_status": "online", "threat": "malware_download", "date_added": "2026-01-01"},
        ],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("wp_hunter.ingest_abusech.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        records = fetch_urlhaus("test-campaign")

    assert len(records) == 1
    assert records[0]["domain"] == "wordpress-site.com"
    assert records[0]["source"] == "urlhaus"
    assert records[0]["campaign_id"] == "test-campaign"


def test_fetch_urlhaus_handles_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {"query_status": "no_results"}
    mock_response.raise_for_status = MagicMock()

    with patch("wp_hunter.ingest_abusech.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        records = fetch_urlhaus("test-campaign")

    assert records == []


def test_fetch_threatfox_filters_url_type():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "query_status": "ok",
        "data": [
            {"ioc": "http://evil.com/loader.php", "ioc_type": "url", "malware": "wp_loader", "id": "1", "threat_type": "payload_delivery", "first_seen": "2026-01-01", "confidence_level": 80, "malware_printable": "WP Loader"},
            {"ioc": "1.2.3.4", "ioc_type": "ip:port", "malware": "botnet", "id": "2"},
        ],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("wp_hunter.ingest_abusech.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        records = fetch_threatfox("test-campaign")

    assert len(records) == 1
    assert records[0]["domain"] == "evil.com"
    assert records[0]["source"] == "threatfox"
