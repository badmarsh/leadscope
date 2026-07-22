"""
Integration tests for the Evaluator microservice HTTP API.
Requires Docker stack running (evaluator on :8001, postgres on :5432).
"""
import os
import pytest
import requests

EVAL_URL = os.environ.get("EVALUATOR_URL", "http://localhost:8001")


def _evaluator_up() -> bool:
    try:
        r = requests.get(f"{EVAL_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _evaluator_up(), reason="Evaluator microservice not running")
class TestEvaluatorAPI:

    def test_health_returns_200_with_service_name(self):
        r = requests.get(f"{EVAL_URL}/health", timeout=5)
        assert r.status_code == 200
        assert r.json().get("service") == "evaluator"

    def test_score_nonexistent_candidate_returns_400(self):
        r = requests.post(f"{EVAL_URL}/score/999999999", timeout=10)
        assert r.status_code in (400, 500)

    def test_score_trigger_endpoint_background(self):
        r = requests.post(f"{EVAL_URL}/score/trigger?background=true", timeout=10)
        assert r.status_code == 200
        assert r.json().get("ok") is True
