import pytest
from unittest.mock import patch, MagicMock
from services.jobs.rescore_icp import rescore_outdated_candidates

@patch('services.jobs.rescore_icp.get_db')
@patch('services.jobs.rescore_icp.requests.post')
def test_rescore_outdated_candidates(mock_post, mock_get_db):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    mock_cur.fetchall.side_effect = [
        # current_icp_versions
        [(1, 2)], 
        # candidates
        [
            (101, 1, 1), # old version, should rescore
            (102, 1, 2), # current version, should skip
            (103, 1, None) # no version, should skip
        ]
    ]
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    rescore_outdated_candidates()
    
    mock_post.assert_called_once_with("http://localhost:8000/score/101", timeout=60)
    mock_cur.execute.assert_called_with("DELETE FROM evaluations WHERE candidate_id = %s AND icp_version_used < %s", (101, 2))
