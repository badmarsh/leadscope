import pytest
import json
from unittest.mock import patch, MagicMock
from services.jobs.ingest_hunters import ingest_findings

@pytest.fixture
def mock_db():
    with patch("services.jobs.ingest_hunters.get_db_connection") as mock_get_conn:
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        mock_get_conn.return_value = conn
        yield conn, cursor

def test_ingest_findings_missing_slug_skipped(mock_db, tmp_path, capsys):
    conn, cursor = mock_db
    # Mock the campaign table mapping
    cursor.fetchall.return_value = [(1, "known-slug")]
    
    findings_file = tmp_path / "findings.jsonl"
    findings_file.write_text(json.dumps({"domain": "test.com", "campaign_id": "unknown-slug"}))
    
    ingest_findings(findings_file)
    
    # Assert no inserts occurred
    assert cursor.execute.call_count == 1 # Only the SELECT campaigns ran
    out, _ = capsys.readouterr()
    assert "Campaign slug 'unknown-slug' not found in DB" in out

def test_ingest_findings_valid_inserts(mock_db, tmp_path):
    conn, cursor = mock_db
    # Mock the campaign table mapping
    cursor.fetchall.return_value = [(1, "known-slug")]
    cursor.rowcount = 1
    
    findings_file = tmp_path / "findings.jsonl"
    data = {"domain": "test.com", "campaign_id": "known-slug", "source": "urlscan"}
    findings_file.write_text(json.dumps(data))
    
    ingest_findings(findings_file)
    
    # Assert insert occurred
    assert cursor.execute.call_count == 2
    query, args = cursor.execute.call_args_list[1][0]
    assert "INSERT INTO candidates" in query
    assert args[0] == "test.com"
    assert args[1] == "urlscan"
    assert args[3] == 1 # campaign_id
    # Assert commit was called
    conn.commit.assert_called_once()

def test_ingest_findings_handles_empty_lines(mock_db, tmp_path):
    conn, cursor = mock_db
    cursor.fetchall.return_value = [(1, "known-slug")]
    cursor.rowcount = 1
    
    findings_file = tmp_path / "findings.jsonl"
    lines = [
        "",
        json.dumps({"domain": "test.com", "campaign_id": "known-slug"}),
        "   ",
        json.dumps({"domain": "test2.com", "campaign_id": "known-slug"})
    ]
    findings_file.write_text("\n".join(lines))
    
    ingest_findings(findings_file)
    
    assert cursor.execute.call_count == 3 # 1 SELECT + 2 INSERTs
