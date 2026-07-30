import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import icp_drift_job

@patch("icp_drift_job.analyze_drift")
@patch("icp_drift_job.db.fetchall")
@patch("icp_drift_job.db.get_conn")
def test_icp_drift_job_run(mock_get_conn, mock_fetchall, mock_analyze_drift):
    mock_conn = MagicMock()
    mock_get_conn.return_value.__enter__.return_value = mock_conn
    mock_fetchall.return_value = [{"id": 1}, {"id": 2}]
    mock_analyze_drift.side_effect = [{"drift_detected": True}, None]

    icp_drift_job.run()

    mock_fetchall.assert_called_once_with(mock_conn, "SELECT id FROM campaigns")
    assert mock_analyze_drift.call_count == 2
    mock_analyze_drift.assert_any_call(1)
    mock_analyze_drift.assert_any_call(2)
