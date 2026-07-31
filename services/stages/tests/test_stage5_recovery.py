import os
import sys
import pytest
from unittest.mock import patch, MagicMock

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

# Mock extruct and w3lib before importing stage5
sys.modules["extruct"] = MagicMock()
mock_w3lib = MagicMock()
sys.modules["w3lib"] = mock_w3lib
sys.modules["w3lib.html"] = mock_w3lib

import stage5

@patch("stage5.db")
def test_recover_stuck_enrichments(mock_db):
    mock_conn = MagicMock()
    mock_db.execute.return_value = 3
    
    with patch("stage5.logger.warning") as mock_logger:
        stage5._recover_stuck_enrichments(mock_conn)
        
        mock_db.execute.assert_called_once()
        args, kwargs = mock_db.execute.call_args
        assert mock_conn == args[0]
        query = args[1]
        assert "UPDATE candidates" in query
        assert "enrichment_attempt_count = GREATEST(0, enrichment_attempt_count - 1)" in query
        assert "status IN ('evaluated', 'enriched', 'pending_review', 'approved')" in query
        
        mock_logger.assert_called_once_with("Stage 5 crash recovery: reset %d stuck enrichment attempts.", 3)

@patch("stage5.db")
def test_recover_stuck_enrichments_no_rows(mock_db):
    mock_conn = MagicMock()
    mock_db.execute.return_value = 0
    
    with patch("stage5.logger.warning") as mock_logger:
        stage5._recover_stuck_enrichments(mock_conn)
        mock_logger.assert_not_called()
