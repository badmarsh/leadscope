"""
tests/test_harness_ai_evaluator.py — Stage 3: AI Evaluator / Scoring Harness

Tests the evaluator orchestration pipeline:
  - Scorer registry (all types registered)
  - _status_from_score threshold logic (approved vs discarded)
  - _select_scorer fallback for unknown evaluator_type
  - score_candidate: DNC → immediate discard
  - score_candidate: Duplicate detection → "duplicate" status
  - score_candidate: Budget ceiling → return to 'new'
  - score_candidate: LLM cognitive failure (1st attempt → retry, 3rd attempt → discard)
  - score_candidate: URLScan bonus only when snippet confirmed
  - score_candidate: Optimistic concurrency abort (candidate reset during scoring)
  - trigger_scoring: sends only 'active' campaigns to evaluator
  - trigger_scoring: respects evaluator_batch_size setting
  - _load_few_shot: only uses feedback from same campaign
  - _load_icp: returns empty dict when no ICP exists
"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import harness
from harness import (
    SCORER_REGISTRY,
    _status_from_score,
    _select_scorer,
    score_candidate,
    trigger_scoring,
)


# ── Scorer registry ────────────────────────────────────────────────────────────

class TestScorerRegistry:
    def test_all_expected_scorers_registered(self):
        for key in ["content_relevance", "image_quality", "threat_intel",
                    "threat_intel_fast", "auto", "performance_gap",
                    "gdpr_gap", "accessibility_risk"]:
            assert key in SCORER_REGISTRY, f"Missing scorer: {key}"

    def test_auto_maps_to_content_relevance(self):
        assert SCORER_REGISTRY["auto"] is SCORER_REGISTRY["content_relevance"]


# ── _status_from_score threshold ───────────────────────────────────────────────

class TestStatusFromScore:
    def test_above_min_score_is_approved(self):
        assert _status_from_score(50, min_score=20) == "approved"

    def test_exactly_at_min_score_is_approved(self):
        assert _status_from_score(20, min_score=20) == "approved"

    def test_below_min_score_is_discarded(self):
        assert _status_from_score(19, min_score=20) == "discarded"

    def test_is_shitty_flag_overrides_score(self):
        assert _status_from_score(95, min_score=20, is_shitty=True) == "discarded"

    def test_zero_score_is_discarded(self):
        assert _status_from_score(0, min_score=20) == "discarded"

    def test_perfect_score_is_approved(self):
        assert _status_from_score(100, min_score=20) == "approved"


# ── _select_scorer fallback ────────────────────────────────────────────────────

class TestSelectScorer:
    def test_known_type_returns_correct_fn(self):
        campaign = {"id": 1, "evaluator_type": "content_relevance"}
        fn = _select_scorer(campaign)
        assert fn is SCORER_REGISTRY["content_relevance"]

    def test_unknown_type_falls_back_to_content_relevance(self):
        campaign = {"id": 1, "evaluator_type": "totally_unknown_scorer"}
        fn = _select_scorer(campaign)
        assert fn is SCORER_REGISTRY["content_relevance"]

    def test_none_type_falls_back_to_content_relevance(self):
        campaign = {"id": 1, "evaluator_type": None}
        fn = _select_scorer(campaign)
        assert fn is SCORER_REGISTRY["content_relevance"]

    def test_missing_key_falls_back_to_content_relevance(self):
        campaign = {"id": 1}
        fn = _select_scorer(campaign)
        assert fn is SCORER_REGISTRY["content_relevance"]


# ── score_candidate: DNC ───────────────────────────────────────────────────────

class TestScoreCandidateDNC:
    @patch("harness.db")
    def test_dnc_candidate_is_discarded(self, mock_db):
        mock_db.fetchone.side_effect = [
            # 1. candidate
            {"id": 1, "domain": "blocked.com", "campaign_id": 1, "source": "exa",
             "query_used": "kw", "evidence_data": "{}", "status": "new",
             "company_name": "Blocked Co", "processing_generation": 0},
            # 2. campaign
            {"id": 1, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            # 3. DNC check → hit
            {"1": 1},
        ]
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock

        result = score_candidate(1)

        assert result["score"] == 0
        assert "Do Not Contact" in result["rationale"]
        mock_db.update_candidate_generation.assert_called_with(
            conn_mock, 1, 0, {"status": "discarded"}
        )


# ── score_candidate: Duplicate ────────────────────────────────────────────────

class TestScoreCandidateDuplicate:
    @patch("harness.db")
    def test_duplicate_candidate_gets_duplicate_status(self, mock_db):
        mock_db.fetchone.side_effect = [
            # 1. candidate
            {"id": 5, "domain": "dup.com", "campaign_id": 2, "source": "exa",
             "query_used": "kw", "evidence_data": "{}", "status": "new",
             "company_name": "Dup Co", "processing_generation": 0},
            # 2. campaign
            {"id": 2, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            # 3. DNC check → not on list
            None,
            # 4. duplicate check → found original
            {"id": 3},
        ]
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock

        result = score_candidate(5)

        assert result["score"] == 0
        assert "Duplicate" in result["rationale"]
        mock_db.update_candidate_generation.assert_called_with(
            conn_mock, 5, 0, {"status": "duplicate", "duplicate_of_candidate_id": 3}
        )


# ── score_candidate: Budget ceiling ───────────────────────────────────────────

class TestScoreCandidateBudgetCeiling:
    @patch("harness.cost_gate")
    @patch("harness.db")
    def test_returns_to_new_when_budget_exceeded(self, mock_db, mock_cost_gate):
        mock_db.fetchone.side_effect = [
            # 1. candidate
            {"id": 10, "domain": "ok.com", "campaign_id": 1, "source": "exa",
             "query_used": "kw", "evidence_data": "{}", "status": "new",
             "company_name": "OK Co", "processing_generation": 0},
            # 2. campaign
            {"id": 1, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            # 3. DNC → no hit
            None,
            # 4. duplicate → no hit
            None,
            # 5. _load_icp → no ICP configured
            None,
        ]
        mock_db.fetchall.return_value = []  # _load_few_shot returns empty
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock

        mock_cost_gate.check_budget.return_value = False

        result = score_candidate(10)

        assert result["score"] == 0
        assert "Budget" in result["rationale"]
        mock_db.update_candidate_generation.assert_called_with(
            conn_mock, 10, 0, {"status": "new"}
        )


# ── score_candidate: LLM cognitive failure ─────────────────────────────────────

class TestScoreCandidateCognitiveFailure:
    def _make_candidate_side_effect(self, eval_attempts=0):
        return [
            {"id": 20, "domain": "fail.com", "campaign_id": 1, "source": "exa",
             "query_used": "kw",
             # evidence_data as dict — harness calls .get() on it directly without json.loads
             "evidence_data": {"eval_attempts": eval_attempts},
             "status": "new", "company_name": "Fail Co", "processing_generation": 0},
            {"id": 1, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            None,  # DNC
            None,  # dup
            None,  # _load_icp (no ICP)
        ]

    @patch("harness.cost_gate")
    @patch("harness._select_scorer")
    @patch("harness.db")
    def test_first_failure_resets_to_new_for_retry(self, mock_db, mock_scorer, mock_cost_gate):
        mock_db.fetchone.side_effect = self._make_candidate_side_effect(eval_attempts=0)
        mock_db.fetchall.return_value = []  # few-shot empty
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_cost_gate.check_budget.return_value = True

        # Scorer returns a raw (non-JSON) response — cognitive failure
        mock_scorer.return_value = lambda c, ca, i, f: {"_raw": "Sorry cannot evaluate", "score": 0}

        result = score_candidate(20)

        assert "retry" in result["rationale"].lower() or "cognitive failure" in result["rationale"].lower()
        update_call = mock_db.update_candidate_generation.call_args
        assert update_call[0][3]["status"] == "new"

    @patch("harness.cost_gate")
    @patch("harness._select_scorer")
    @patch("harness.db")
    def test_third_failure_discards_candidate(self, mock_db, mock_scorer, mock_cost_gate):
        mock_db.fetchone.side_effect = self._make_candidate_side_effect(eval_attempts=2)
        mock_db.fetchall.return_value = []
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_cost_gate.check_budget.return_value = True

        mock_scorer.return_value = lambda c, ca, i, f: {"_raw": "Still cannot evaluate", "score": 0}

        result = score_candidate(20)

        assert "discarded" in result["rationale"].lower() or "cognitive failure" in result["rationale"].lower()
        update_call = mock_db.update_candidate_generation.call_args
        assert update_call[0][3]["status"] == "discarded"


# ── score_candidate: URLScan bonus ─────────────────────────────────────────────

class TestScoreCandidateURLScanBonus:
    def _make_urlscan_candidate_mocks(self, snippet_confirmed: bool):
        return [
            {"id": 30, "domain": "urlscan-site.com", "campaign_id": 1,
             "source": "urlscan",  # ← URLScan source
             "query_used": "wp", "evidence_data": "{}", "status": "new",
             "company_name": "URLScan Co", "processing_generation": 0},
            {"id": 1, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            None,  # DNC
            None,  # dup
            None,  # ICP check (version 0)
        ]

    @patch("harness.cost_gate")
    @patch("harness._select_scorer")
    @patch("harness.db")
    def test_urlscan_bonus_applied_when_snippet_confirmed(self, mock_db, mock_scorer, mock_cost_gate):
        mock_db.fetchone.side_effect = self._make_urlscan_candidate_mocks(snippet_confirmed=True) + [
            {"status": "evaluating"},  # concurrency check
        ]
        mock_db.fetchall.return_value = []
        mock_db.execute_returning.return_value = {"id": 500, "score": 75, "icp_version_used": 1}
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_cost_gate.check_budget.return_value = True

        mock_scorer.return_value = lambda c, ca, i, f: {
            "score": 55,
            "rationale": "Good site",
            "evidence_data": {"snippet_confirmed": True},
            "evidence_urls": [],
            "model_used": "gemini",
        }

        result = score_candidate(30)
        # Default bonus is 20 → 55 + 20 = 75
        assert result["score"] == 75

    @patch("harness.cost_gate")
    @patch("harness._select_scorer")
    @patch("harness.db")
    def test_urlscan_no_bonus_when_snippet_not_confirmed(self, mock_db, mock_scorer, mock_cost_gate):
        mock_db.fetchone.side_effect = self._make_urlscan_candidate_mocks(snippet_confirmed=False) + [
            {"status": "evaluating"},
        ]
        mock_db.fetchall.return_value = []
        mock_db.execute_returning.return_value = {"id": 501, "score": 55, "icp_version_used": 1}
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_cost_gate.check_budget.return_value = True

        mock_scorer.return_value = lambda c, ca, i, f: {
            "score": 55,
            "rationale": "Good site",
            "evidence_data": {"snippet_confirmed": False},
            "evidence_urls": [],
            "model_used": "gemini",
        }

        result = score_candidate(30)
        assert result["score"] == 55  # No bonus applied
        assert "Unconfirmed" in result["rationale"]


# ── score_candidate: Optimistic concurrency ────────────────────────────────────

class TestScoreCandidateConcurrency:
    @patch("harness.cost_gate")
    @patch("harness._select_scorer")
    @patch("harness.db")
    def test_abort_when_candidate_reset_during_scoring(self, mock_db, mock_scorer, mock_cost_gate):
        """If candidate status changed from 'evaluating' during scoring, abort and do not save."""
        mock_db.fetchone.side_effect = [
            {"id": 40, "domain": "race.com", "campaign_id": 1, "source": "exa",
             "query_used": "kw", "evidence_data": "{}", "status": "new",
             "company_name": "Race Co", "processing_generation": 0},
            {"id": 1, "evaluator_type": "content_relevance", "slug": "test",
             "name": "Test", "business_brief": "brief", "settings": "{}"},
            None,  # DNC
            None,  # dup
            None,  # ICP
            # Concurrency check: status is NOT 'evaluating' anymore (user reset it)
            {"status": "new"},
        ]
        mock_db.fetchall.return_value = []
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_cost_gate.check_budget.return_value = True

        mock_scorer.return_value = lambda c, ca, i, f: {
            "score": 80,
            "rationale": "Great",
            "evidence_data": {},
            "evidence_urls": [],
            "model_used": "gemini",
        }

        result = score_candidate(40)

        assert result.get("aborted") is True
        mock_db.execute_returning.assert_not_called()  # No INSERT into evaluations


# ── trigger_scoring: active campaigns only ─────────────────────────────────────

class TestTriggerScoring:
    @patch("harness.db")
    def test_queries_only_active_campaigns(self, mock_db):
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_db.fetchall.return_value = []
        mock_db.execute.return_value = 1

        trigger_scoring()

        all_queries = [c[0][1] for c in mock_db.fetchall.call_args_list]
        assert any("status = 'active'" in q for q in all_queries)

    @patch("harness.score_candidate")
    @patch("harness.db")
    def test_respects_evaluator_batch_size(self, mock_db, mock_score):
        """Campaign with evaluator_batch_size=5 should only claim 5 candidates."""
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_db.fetchone.return_value = {"settings": '{"evaluator_batch_size": 5}'}
        mock_db.claim_candidates_for_stage.return_value = []
        mock_db.check_stop_signal.return_value = False
        mock_db.acquire_stage_lock.return_value = True
        mock_db.execute.return_value = 1

        trigger_scoring(campaign_id=1)

        calls = mock_db.claim_candidates_for_stage.call_args_list
        if calls:
            # claim_candidates_for_stage is called with keyword args
            kwargs = calls[0][1]
            limit_val = kwargs.get("limit", None)
            assert limit_val == 5, f"Expected limit=5, got {limit_val}"

    @patch("harness.score_candidate")
    @patch("harness.db")
    def test_processes_all_claimed_candidates(self, mock_db, mock_score):
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_db.fetchone.return_value = {"settings": "{}"}
        mock_db.claim_candidates_for_stage.return_value = [
            {"id": 1, "campaign_id": 1, "domain": "a.com", "company_name": "A", "processing_generation": 1},
            {"id": 2, "campaign_id": 1, "domain": "b.com", "company_name": "B", "processing_generation": 1},
            {"id": 3, "campaign_id": 1, "domain": "c.com", "company_name": "C", "processing_generation": 1},
        ]
        mock_db.check_stop_signal.return_value = False
        mock_db.acquire_stage_lock.return_value = True
        mock_db.execute.return_value = 1
        mock_score.return_value = {"score": 75, "rationale": "ok", "evidence_data": {}}

        trigger_scoring(campaign_id=1)

        assert mock_score.call_count == 3

    @patch("harness.db")
    def test_stops_processing_on_stop_signal(self, mock_db):
        conn_mock = MagicMock()
        mock_db.get_conn.return_value.__enter__.return_value = conn_mock
        mock_db.fetchone.return_value = {"settings": "{}"}
        mock_db.claim_candidates_for_stage.return_value = [
            {"id": 1, "campaign_id": 1, "domain": "a.com", "company_name": "A", "processing_generation": 1},
        ]
        # Stop signal fires immediately
        mock_db.check_stop_signal.return_value = True
        mock_db.acquire_stage_lock.return_value = True
        mock_db.execute.return_value = 1

        with patch("harness.score_candidate") as mock_score:
            trigger_scoring(campaign_id=1)
            mock_score.assert_not_called()


# ── Few-shot isolation per campaign ────────────────────────────────────────────

class TestLoadFewShot:
    @patch("harness.db")
    def test_few_shot_query_includes_campaign_filter(self, mock_db):
        conn_mock = MagicMock()
        mock_db.fetchall.return_value = []

        from harness import _load_few_shot
        _load_few_shot(conn_mock, campaign_id=42)

        call_args = mock_db.fetchall.call_args
        sql = call_args[0][1]
        params = call_args[0][2]
        assert 42 in params, "Few-shot query must be filtered by campaign_id=42"


# ── ICP loading ────────────────────────────────────────────────────────────────

class TestLoadICP:
    @patch("harness.db")
    def test_returns_empty_when_no_icp(self, mock_db):
        conn_mock = MagicMock()
        mock_db.fetchone.return_value = None

        from harness import _load_icp
        icp, version = _load_icp(conn_mock, campaign_id=1)

        assert icp == {}
        assert version == 0

    @patch("harness.db")
    def test_parses_json_string_fields(self, mock_db):
        conn_mock = MagicMock()
        mock_db.fetchone.return_value = {
            "version": 3,
            "target_segments": '[{"name": "HVAC", "priority": "high"}]',
            "keywords_hu": ["fűtés telepítő"],
            "keywords_en": ["hvac installer"],
            "disqualifiers": '{"exclude_if": ["B2C"], "sectors_out": []}',
        }

        from harness import _load_icp
        icp, version = _load_icp(conn_mock, campaign_id=1)

        assert version == 3
        assert isinstance(icp["target_segments"], list)
        assert icp["target_segments"][0]["name"] == "HVAC"
        assert isinstance(icp["disqualifiers"], dict)
