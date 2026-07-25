import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from seo_spam_hunter.cli import app
from seo_spam_hunter.schema import Campaign, VirusTotalPivot, WaybackPivot

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
        wayback_pivot=WaybackPivot(enabled=True, match_mime="text/html")
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

@patch("seo_spam_hunter.cli.load_campaigns")
@patch("seo_spam_hunter.cli.ingest_publicwww")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_success(mock_ingest, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    result = runner.invoke(app, ["ingest", "--campaign", "test-campaign", "--file", "test.csv"])
    assert result.exit_code == 0
    mock_ingest.assert_called_once()

@patch("seo_spam_hunter.cli.load_campaigns")
@patch("seo_spam_hunter.cli.ingest_abusech")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ingest_feeds_success(mock_ingest_abusech, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    mock_ingest_abusech.return_value = [{"domain": "test.com"}]
    result = runner.invoke(app, ["ingest-feeds", "--campaign", "test-campaign"])
    assert result.exit_code == 0
    mock_ingest_abusech.assert_called_once()

@patch("seo_spam_hunter.cli.load_campaigns")
@patch("seo_spam_hunter.cli.run_ct_monitor")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_ct_monitor_success(mock_ct, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    result = runner.invoke(app, ["ct-monitor", "--campaign", "test-campaign"])
    assert result.exit_code == 0
    mock_ct.assert_called_once()

@patch("seo_spam_hunter.cli.load_campaigns")
@patch("seo_spam_hunter.cli.pivot_urlscan_campaign")
@patch("seo_spam_hunter.cli.pivot_vt_campaign")
@patch("seo_spam_hunter.cli.pivot_wayback_campaign")
@patch("seo_spam_hunter.cli._read_findings")
@patch("seo_spam_hunter.cli._write_findings")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_pivot_success(mock_write, mock_read, mock_wayback, mock_vt, mock_urlscan, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    mock_read.return_value = [{"domain": "existing.com", "campaign_id": "test-campaign"}]
    mock_urlscan.return_value = [{"domain": "urlscan.com"}]
    mock_vt.return_value = [{"domain": "vt.com"}]
    mock_wayback.return_value = [{"domain": "wayback.com"}]
    
    result = runner.invoke(app, ["pivot", "--campaign", "test-campaign", "--wayback"])
    assert result.exit_code == 0
    mock_urlscan.assert_called_once()
    mock_vt.assert_called_once()
    mock_wayback.assert_called_once()
    mock_write.assert_called_once()

@patch("seo_spam_hunter.cli._read_findings")
@patch("seo_spam_hunter.cli.merge_findings")
@patch("seo_spam_hunter.cli.generate_reports")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_report_success(mock_generate, mock_merge, mock_read):
    mock_read.return_value = [{"domain": "test.com"}]
    mock_merge.return_value = [{"domain": "test.com"}]
    
    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    mock_merge.assert_called_once()
    mock_generate.assert_called_once()

@patch("seo_spam_hunter.cli.load_campaigns")
@patch("seo_spam_hunter.cli.ingest_publicwww")
@patch("seo_spam_hunter.cli.pivot_urlscan_campaign")
@patch("seo_spam_hunter.cli.pivot_vt_campaign")
@patch("seo_spam_hunter.cli._read_findings")
@patch("seo_spam_hunter.cli._write_findings")
@patch("seo_spam_hunter.cli.merge_findings")
@patch("seo_spam_hunter.cli.generate_reports")
@pytest.mark.skip(reason="Test-Audit: Too weak, mocks internal logic instead of boundaries")
def test_run_success(mock_gen, mock_merge, mock_write, mock_read, mock_vt, mock_urlscan, mock_ingest, mock_load, mock_campaigns):
    mock_load.return_value = mock_campaigns
    mock_read.return_value = [{"domain": "test.com"}]
    mock_merge.return_value = [{"domain": "test.com"}]
    
    result = runner.invoke(app, ["run", "--campaign", "test-campaign", "--file", "test.csv"])
    assert result.exit_code == 0
