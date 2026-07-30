"""
services/stages/tests/test_watchdog.py
Unit tests for stage health watchdog.
"""
from unittest.mock import patch, MagicMock
from services.stages.watchdog import check_stuck_stages


@patch("services.stages.watchdog.requests.post")
@patch("services.stages.watchdog.db")
def test_check_stuck_stages_alerts_slack(mock_db, mock_post):
    mock_db.fetchall.return_value = [
        {
            "id": 1,
            "slug": "wp-remediation",
            "stage1_status": "running",
            "stage2_status": "idle",
            "stage3_status": "idle",
            "stage5_status": "idle",
        }
    ]
    mock_conn = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = mock_conn

    with patch("services.stages.watchdog.SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
        check_stuck_stages()

    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "STUCK STAGE DETECTED" in payload["text"]
    assert "wp-remediation" in payload["text"]


@patch("services.stages.watchdog.requests.post")
@patch("services.stages.watchdog.db")
def test_check_stuck_stages_no_stuck(mock_db, mock_post):
    mock_db.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = mock_conn

    check_stuck_stages()
    mock_post.assert_not_called()
