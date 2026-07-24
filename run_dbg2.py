import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'services', 'evaluator')))

from unittest.mock import patch, MagicMock

try:
    from harness import trigger_scoring
except ImportError:
    pass

@patch("harness.score_candidate")
@patch("harness.db")
def dbg(mock_db, mock_score):
    mock_db.fetchall.return_value = [
        {"id": 1, "campaign_id": 1, "domain": "jenex.sk", "company_name": "Jenex"}
    ]
    mock_db.fetchone.return_value = {"settings": '{"blocked_domain_terms": ["jenex"]}'}
    mock_db.check_stop_signal.return_value = False
    
    mock_score.return_value = {
        "score": 90,
        "rationale": "Great company",
        "evidence_data": {"photo_quality": "amateur"}
    }
    
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    trigger_scoring(campaign_id=1)
    
    calls = mock_db.execute.call_args_list
    for call in calls:
        print(call)

if __name__ == "__main__":
    dbg()
