"""
tests/test_stage1_brief_analysis.py — Stage 1: Brief Analysis / ICP Definer

Tests the full validation pipeline:
  - ICP schema validation (required keys, types)
  - Keyword quality gates (multi-word, non-empty)
  - Draft campaign gate
  - Stage lock (concurrency)
  - Disqualifiers fallback (list → dict coercion)
  - LLM raw-text response (non-JSON) handling
  - Stage status set to "failed" on error
  - Version increment logic
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

import stage1


# ── Fixtures & helpers ─────────────────────────────────────────────────────────

def _good_icp():
    return {
        "target_segments": [
            {"name": "HVAC installers", "description": "Businesses that install heating.", "priority": "high"},
        ],
        "keywords_hu": ["fűtés telepítő cég Budapest", "kazán szerviz Miskolc"],
        "keywords_en": ["hvac installation company", "boiler service Hungary"],
        "disqualifiers": {
            "exclude_if": ["B2C only"],
            "sectors_out": ["Government"],
        },
    }


def _make_conn_ctx(mock_db_conn):
    """Return a context manager mock that yields mock_db_conn."""
    ctx = MagicMock()
    ctx.__enter__ = lambda s: mock_db_conn
    ctx.__exit__ = lambda s, *a: None
    return ctx


def _patch_stage1(mock_db_conn, icp=None, campaign=None, version_row=None):
    """Common patch stack for stage1.run()."""
    if icp is None:
        icp = _good_icp()
    if campaign is None:
        campaign = {
            "id": 1, "slug": "jenex-hvac", "name": "JENEX HVAC",
            "status": "active", "business_brief": "We install heating systems.",
            "reference_materials": {},
        }
    if version_row is None:
        version_row = {"v": 0}

    def fake_fetchone(conn, sql, params=None):
        if "FROM campaigns" in sql:
            return campaign
        if "MAX(version)" in sql:
            return version_row
        return None

    return (
        patch("stage1.db.get_conn", return_value=_make_conn_ctx(mock_db_conn)),
        patch("stage1.db.acquire_stage_lock", return_value=True),
        patch("stage1.db.set_stage_status"),
        patch("stage1.db.fetchone", side_effect=fake_fetchone),
        patch("stage1.db.execute_returning", return_value={"id": 42, "version": 1}),
        patch("stage1.cost_log.log_call"),
        patch("stage1.llm.chat_json", return_value=(icp, 200, 80, "gemini", "gemini")),
    )


# ── Basic success path ─────────────────────────────────────────────────────────

def test_stage1_success_returns_expected_keys(mock_env, mock_db_conn):
    patches = _patch_stage1(mock_db_conn)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        result = stage1.run(1)

    assert result["campaign_id"] == 1
    assert result["icp_config_id"] == 42
    assert result["version"] == 1
    assert result["segments"] == 1
    assert isinstance(result["keywords_hu"], list)
    assert isinstance(result["keywords_en"], list)
    assert isinstance(result["disqualifiers"], dict)


def test_stage1_version_increments_from_existing(mock_env, mock_db_conn):
    """If there's already a v2, stage1 should produce v3."""
    patches = _patch_stage1(mock_db_conn, version_row={"v": 2})
    with patches[0], patches[1], patches[2], patches[3], patches[4] as mock_exec_ret, patches[5], patches[6]:
        mock_exec_ret.return_value = {"id": 99, "version": 3}
        result = stage1.run(1)
        # The execute_returning was called with version=3
        call_args = mock_exec_ret.call_args
        assert call_args[0][2][1] == 3  # second positional param is version


# ── Concurrency lock ───────────────────────────────────────────────────────────

def test_stage1_skipped_when_lock_not_acquired(mock_env):
    with patch("stage1.db.acquire_stage_lock", return_value=False):
        result = stage1.run(1)
    assert result["status"] == "skipped"
    assert result["reason"] == "already running"


# ── Draft campaign gate ────────────────────────────────────────────────────────

def test_stage1_raises_for_draft_campaign(mock_env, mock_db_conn):
    draft_campaign = {
        "id": 1, "slug": "draft-camp", "name": "Draft",
        "status": "draft", "business_brief": "", "reference_materials": {},
    }
    patches = _patch_stage1(mock_db_conn, campaign=draft_campaign)
    with patches[0], patches[1], patches[2] as mock_set_status, patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="is status='draft'"):
            stage1.run(1)
        mock_set_status.assert_called_with(1, "stage1", "failed")


# ── Campaign not found ─────────────────────────────────────────────────────────

def test_stage1_raises_for_missing_campaign(mock_env, mock_db_conn):
    with patch("stage1.db.get_conn", return_value=_make_conn_ctx(mock_db_conn)), \
         patch("stage1.db.acquire_stage_lock", return_value=True), \
         patch("stage1.db.set_stage_status") as mock_set_status, \
         patch("stage1.db.fetchone", return_value=None):
        with pytest.raises(ValueError, match="not found"):
            stage1.run(999)
        mock_set_status.assert_called_with(999, "stage1", "failed")


# ── LLM response validation ────────────────────────────────────────────────────

@pytest.mark.parametrize("missing_key", ["target_segments", "keywords_hu", "keywords_en", "disqualifiers"])
def test_stage1_raises_on_missing_required_key(mock_env, mock_db_conn, missing_key):
    bad_icp = _good_icp()
    del bad_icp[missing_key]
    patches = _patch_stage1(mock_db_conn, icp=bad_icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="LLM omitted required keys"):
            stage1.run(1)


def test_stage1_raises_on_raw_text_response(mock_env, mock_db_conn):
    """If LLM returns non-JSON (has _raw key), stage1 should raise."""
    raw_icp = {"_raw": "Sorry, I cannot produce JSON right now."}
    patches = _patch_stage1(mock_db_conn, icp=raw_icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="LLM returned non-JSON"):
            stage1.run(1)


def test_stage1_raises_on_empty_keywords_hu(mock_env, mock_db_conn):
    icp = _good_icp()
    icp["keywords_hu"] = []
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="keywords_hu must be a non-empty list"):
            stage1.run(1)


def test_stage1_raises_on_empty_keywords_en(mock_env, mock_db_conn):
    icp = _good_icp()
    icp["keywords_en"] = []
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="keywords_en must be a non-empty list"):
            stage1.run(1)


# ── Keyword quality gate: single-word keywords must be filtered out ────────────

def test_stage1_filters_single_word_keywords_hu(mock_env, mock_db_conn):
    """Single-word keywords like 'website' are too generic and must be purged."""
    icp = _good_icp()
    icp["keywords_hu"] = ["website", "online"]  # both are single-word → should all be filtered → raise
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="multi-word queries"):
            stage1.run(1)


def test_stage1_passes_mixed_keywords_hu(mock_env, mock_db_conn):
    """If some single-word keywords are mixed in, they get stripped; valid multi-word ones remain."""
    icp = _good_icp()
    icp["keywords_hu"] = ["website", "fűtés telepítő cég Budapest", "online"]
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        result = stage1.run(1)
    assert result["keywords_hu"] == ["fűtés telepítő cég Budapest"]


def test_stage1_filters_single_word_keywords_en(mock_env, mock_db_conn):
    icp = _good_icp()
    icp["keywords_en"] = ["hvac", "boiler"]  # both single-word → raise
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(ValueError, match="multi-word queries"):
            stage1.run(1)


# ── Disqualifiers coercion: list → dict ───────────────────────────────────────

def test_stage1_coerces_list_disqualifiers_to_dict(mock_env, mock_db_conn):
    """LLM sometimes returns disqualifiers as a list instead of a dict. Stage 1 must coerce it."""
    icp = _good_icp()
    icp["disqualifiers"] = ["no B2C", "no government"]  # list, not dict
    patches = _patch_stage1(mock_db_conn, icp=icp)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        result = stage1.run(1)
    assert isinstance(result["disqualifiers"], dict)
    assert "exclude_if" in result["disqualifiers"]
    assert "sectors_out" in result["disqualifiers"]


# ── Stage status lifecycle ─────────────────────────────────────────────────────

def test_stage1_sets_status_to_idle_on_success(mock_env, mock_db_conn):
    patches = _patch_stage1(mock_db_conn)
    with patches[0], patches[1], patches[2], patches[3] as mock_fetch, patches[4], patches[5], patches[6]:
        with patch("stage1.db.set_stage_status") as mock_status:
            stage1.run(1)
            mock_status.assert_called_with(1, "stage1", "idle")


def test_stage1_sets_status_to_failed_on_llm_error(mock_env, mock_db_conn):
    patches = _patch_stage1(mock_db_conn)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        with patch("stage1.db.set_stage_status") as mock_status, \
             patch("stage1.llm.chat_json", side_effect=RuntimeError("LLM timeout")):
            with pytest.raises(RuntimeError):
                stage1.run(1)
            mock_status.assert_called_with(1, "stage1", "failed")
