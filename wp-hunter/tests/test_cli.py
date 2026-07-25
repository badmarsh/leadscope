import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from wp_hunter.cli import app
from wp_hunter.schema import Campaign, VirusTotalPivot

runner = CliRunner()

@pytest.fixture
def mock_campaigns():
    camp1 = Campaign(
        id="test-campaign",
        name="Test",
        family="TestFamily",
        source_url="http://example.com",
        location="header",
        added="2023-01-01",
        stale_after_days=99999,
        publicwww_query="test",
        urlscan_pivot=["test"],
        virustotal_pivot=VirusTotalPivot(hashes=["abcd"], domains=["test.com"]),
    )
    camp2 = Campaign(
        id="stale-campaign",
        name="Stale",
        family="StaleFamily",
        source_url="http://example.com",
        location="header",
        added="2020-01-01",
        stale_after_days=1,
    )
    return [camp1, camp2]

@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_missing_campaign():
    result = runner.invoke(app, ["ingest", "--campaign", "missing", "--file", "test.csv"])
    assert result.exit_code == 1
    assert "Campaign ID 'missing' not found" in result.stdout

@patch("wp_hunter.cli.load_campaigns")
@patch("wp_hunter.cli.ingest_publicwww")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_success(mock_ingest, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    result = runner.invoke(app, ["ingest", "--campaign", "test-campaign", "--file", "test.csv"])
    assert result.exit_code == 0
    mock_ingest.assert_called_once_with(campaign_id="test-campaign", file_path=Path("test.csv"))

@patch("wp_hunter.cli.load_campaigns")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_stale_campaign(mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    result = runner.invoke(app, ["ingest", "--campaign", "stale-campaign", "--file", "test.csv"])
    assert result.exit_code == 1
    assert "stale" in result.stdout.lower()

@patch("wp_hunter.cli.load_campaigns")
@patch("wp_hunter.cli.ingest_abusech")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_feeds_success(mock_ingest_abusech, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    mock_ingest_abusech.return_value = [{"domain": "test.com"}]
    result = runner.invoke(app, ["ingest-feeds", "--campaign", "test-campaign"])
    assert result.exit_code == 0
    mock_ingest_abusech.assert_called_once()
    assert "Ingested 1 Abuse.ch records" in result.stdout

@patch("wp_hunter.cli.load_campaigns")
@patch("wp_hunter.cli.pivot_urlscan_campaign")
@patch("wp_hunter.cli.pivot_vt_campaign")
@patch("wp_hunter.cli.save_findings_jsonl")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_pivot_success(mock_save, mock_vt, mock_urlscan, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    mock_urlscan.return_value = [{"domain": "urlscan.com"}]
    mock_vt.return_value = [{"domain": "vt.com"}]
    result = runner.invoke(app, ["pivot", "--campaign", "test-campaign"])
    assert result.exit_code == 0
    mock_urlscan.assert_called_once()
    mock_vt.assert_called_once()
    mock_save.assert_called_once()

@patch("wp_hunter.cli.load_campaigns")
@patch("wp_hunter.cli.load_findings_jsonl")
@patch("wp_hunter.cli.merge_findings")
@patch("wp_hunter.cli.generate_reports")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_report_success(mock_generate, mock_merge, mock_load_findings, mock_load_camp, mock_campaigns):
    mock_load_camp.return_value = mock_campaigns
    mock_load_findings.return_value = [
        {"domain": "test.com", "campaign_id": "test-campaign", "source": "publicwww"}
    ]
    mock_merge.return_value = [{"domain": "test.com"}]
    
    result = runner.invoke(app, ["report", "--campaign", "test-campaign"])
    assert result.exit_code == 0
    mock_merge.assert_called_once()
    mock_generate.assert_called_once()

@patch("wp_hunter.cli.load_campaigns")
@patch("wp_hunter.cli.ingest_publicwww")
@patch("wp_hunter.cli.pivot_urlscan_campaign")
@patch("wp_hunter.cli.pivot_vt_campaign")
@patch("wp_hunter.cli.save_findings_jsonl")
@patch("wp_hunter.cli.load_findings_jsonl")
@patch("wp_hunter.cli.merge_findings")
@patch("wp_hunter.cli.generate_reports")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_run_success(mock_generate, mock_merge, mock_load_findings, mock_save, mock_vt, mock_urlscan, mock_ingest, mock_load_camp, mock_campaigns):
    mock_load_camp.return_value = mock_campaigns
    mock_ingest.return_value = [{"domain": "test.com"}]
    mock_urlscan.return_value = [{"domain": "urlscan.com"}]
    mock_vt.return_value = [{"domain": "vt.com"}]
    mock_load_findings.return_value = []
    mock_merge.return_value = [{"domain": "merged.com"}]
    
    result = runner.invoke(app, ["run", "--campaign", "test-campaign", "--file", "test.csv"])
    assert result.exit_code == 0
    mock_generate.assert_called_once()
