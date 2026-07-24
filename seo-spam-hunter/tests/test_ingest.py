from pathlib import Path
import pytest
from seo_spam_hunter.ingest import (
    clean_domain,
    ingest_publicwww,
    is_redacted,
    parse_csv_export,
    parse_text_paste,
)


def test_is_redacted():
    assert is_redacted("***masked.com") is True
    assert is_redacted("<private>") is True
    assert is_redacted("example.com", snippet="Upgrade to view") is True
    assert is_redacted("clean-domain.org", snippet="var ndsw=1;") is False


def test_clean_domain():
    assert clean_domain("https://example.com/path?query=1") == "example.com"
    assert clean_domain("http://sub.domain.org:8080/") == "domain.org"


def test_parse_csv_export():
    csv_file = Path(__file__).parent / "fixtures" / "publicwww_csv.csv"
    results = parse_csv_export(csv_file)
    assert len(results) == 5
    assert results[0]["visible"] is True
    assert results[0]["domain"] == "example.com"
    assert results[1]["visible"] is False
    assert results[3]["visible"] is False


def test_parse_text_paste():
    paste_file = Path(__file__).parent / "fixtures" / "publicwww_paste.txt"
    content = paste_file.read_text(encoding="utf-8")
    results = parse_text_paste(content)
    assert len(results) == 3
    assert results[0]["visible"] is True
    assert results[1]["visible"] is False


def test_ingest_publicwww_append(tmp_path):
    findings_file = tmp_path / "findings.jsonl"
    csv_file = Path(__file__).parent / "fixtures" / "publicwww_csv.csv"

    ingest_publicwww(campaign_id="test-camp", file_path=csv_file, findings_file=findings_file)
    lines = findings_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5

    # Re-run ingest for same campaign to confirm deduplication
    ingest_publicwww(campaign_id="test-camp", file_path=csv_file, findings_file=findings_file)
    lines = findings_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5

    # Run ingest for a different campaign to confirm append
    ingest_publicwww(campaign_id="test-camp-2", file_path=csv_file, findings_file=findings_file)
    lines = findings_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 10

