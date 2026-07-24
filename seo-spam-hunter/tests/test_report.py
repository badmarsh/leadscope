import json
import csv
from seo_spam_hunter.report import generate_reports

def test_generate_reports(tmp_path):
    merged_findings = [
        {
            "domain": "test.com",
            "campaign_id": "test_camp",
            "confidence": "confirmed",
            "publicwww_visible": True,
            "urlscan_scans": [{"scan_id": "123", "screenshot_url": "http://img"}]
        }
    ]

    generate_reports(merged_findings, output_dir=tmp_path)
    
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.csv").exists()
    assert (tmp_path / "report.md").exists()

    with (tmp_path / "report.json").open() as f:
        data = json.load(f)
        assert data[0]["domain"] == "test.com"
        
    with (tmp_path / "report.csv").open() as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert row["domain"] == "test.com"

def test_generate_reports_with_edges(tmp_path):
    merged_findings = [{"domain": "test.com", "campaign_id": "c1"}]
    edges = [{"Source": "test.com", "Target": "other.com", "Type": "wayback_shared"}]
    generate_reports(merged_findings, edge_list=edges, output_dir=tmp_path)
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report_edges.csv").exists()
    
    with (tmp_path / "report_edges.csv").open() as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert row["Source"] == "test.com"
        assert row["Target"] == "other.com"
