import pytest
from unittest.mock import patch, MagicMock

import stage1

def _mock_icp_json():
    return {
        "target_segments": [
            {"name": "E-commerce", "description": "Online stores.", "priority": "high"}
        ],
        "keywords_hu": ["webáruház", "online bolt"],
        "keywords_en": ["online store", "ecommerce"],
        "disqualifiers": {
            "exclude_if": ["B2B"],
            "sectors_out": ["Government"]
        }
    }

def test_run_stage1_success(mock_env, mock_db_conn):
    def fake_fetchone(conn, sql, params=None):
        if "FROM campaigns" in sql:
            return {
                "id": 1,
                "slug": "test",
                "name": "Test",
                "status": "active",
                "business_brief": "We sell security.",
                "reference_materials": {}
            }
        if "MAX(version)" in sql:
            return {"v": 0}
        return None

    def fake_execute_returning(conn, sql, params=None):
        return {"id": 100, "version": 1}

    mock_icp = _mock_icp_json()

    with patch("stage1.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("stage1.db.acquire_stage_lock", return_value=True), \
         patch("stage1.db.set_stage_status"), \
         patch("stage1.db.fetchone", side_effect=fake_fetchone), \
         patch("stage1.db.execute_returning", side_effect=fake_execute_returning), \
         patch("stage1.cost_log.log_call"), \
         patch("stage1.llm.chat_json", return_value=(mock_icp, 100, 50)):
         
         result = stage1.run(1)
         
         assert result["campaign_id"] == 1
         assert result["icp_config_id"] == 100
         assert result["version"] == 1
         assert result["segments"] == 1
         assert len(result["keywords_hu"]) == 2
         assert len(result["keywords_en"]) == 2

def test_run_stage1_skipped_if_locked(mock_env):
    with patch("stage1.db.acquire_stage_lock", return_value=False):
        result = stage1.run(1)
        assert result["status"] == "skipped"
        assert result["reason"] == "already running"

def test_run_stage1_fails_on_draft(mock_env, mock_db_conn):
    def fake_fetchone(conn, sql, params=None):
        return {
            "id": 1,
            "slug": "test",
            "name": "Test",
            "status": "draft",
            "business_brief": "Draft brief.",
            "reference_materials": {}
        }

    with patch("stage1.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("stage1.db.acquire_stage_lock", return_value=True), \
         patch("stage1.db.set_stage_status") as mock_set_status, \
         patch("stage1.db.fetchone", side_effect=fake_fetchone):
         
         with pytest.raises(ValueError, match="is status='draft'"):
             stage1.run(1)
             
         mock_set_status.assert_called_with(1, "stage1", "failed")

def test_run_stage1_invalid_llm_json(mock_env, mock_db_conn):
    def fake_fetchone(conn, sql, params=None):
        if "FROM campaigns" in sql:
            return {
                "id": 1,
                "slug": "test",
                "name": "Test",
                "status": "active",
                "business_brief": "We sell security.",
                "reference_materials": {}
            }
        return {"v": 0}

    def fake_execute_returning(conn, sql, params=None):
        return {"id": 100, "version": 1}

    bad_json = _mock_icp_json()
    del bad_json["target_segments"]  # Missing required key

    with patch("stage1.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("stage1.db.acquire_stage_lock", return_value=True), \
         patch("stage1.db.set_stage_status"), \
         patch("stage1.db.fetchone", side_effect=fake_fetchone), \
         patch("stage1.db.execute_returning", side_effect=fake_execute_returning), \
         patch("stage1.cost_log.log_call"), \
         patch("stage1.llm.chat_json", return_value=(bad_json, 10, 5)):
         
         res = stage1.run(1)
         assert res["campaign_id"] == 1
