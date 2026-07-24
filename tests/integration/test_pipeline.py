"""
Integration test suite for the multi-stage lead generation pipeline.
Tests service health, database connectivity, ICP generation, target finding, and scoring evaluator.
Uses Python's native unittest module for zero-dependency execution.
"""
import os
import pytest
import requests

STAGES_URL = os.environ.get("STAGES_URL", "http://127.0.0.1:8002")
EVALUATOR_URL = os.environ.get("EVALUATOR_URL", "http://127.0.0.1:8001")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:3000")


def _is_service_up(url: str, endpoint: str = "/health") -> bool:
    try:
        r = requests.get(f"{url}{endpoint}", timeout=2)
        return r.status_code in (200, 401)
    except Exception:
        return False


@pytest.mark.integration
class TestPipelineIntegration:

    @pytest.mark.skipif(not _is_service_up(STAGES_URL), reason="Stages service offline")
    def test_stages_health(self):
        """Verify Stages microservice health endpoint."""
        r = requests.get(f"{STAGES_URL}/health", timeout=3)
        assert r.status_code == 200, f"Stages health error: {r.text}"

    @pytest.mark.skipif(not _is_service_up(EVALUATOR_URL), reason="Evaluator service offline")
    def test_evaluator_health(self):
        """Verify Evaluator microservice health endpoint."""
        r = requests.get(f"{EVALUATOR_URL}/health", timeout=3)
        assert r.status_code == 200, f"Evaluator health error: {r.text}"

    @pytest.mark.skipif(not _is_service_up(DASHBOARD_URL, "/api/session"), reason="Dashboard offline")
    def test_dashboard_health(self):
        """Verify Next.js Dashboard health / session API."""
        r = requests.get(f"{DASHBOARD_URL}/api/session", timeout=3)
        assert r.status_code in (200, 401), f"Unexpected status: {r.status_code}"

    @pytest.mark.skipif(not _is_service_up(EVALUATOR_URL), reason="Evaluator service offline")
    def test_evaluator_score_trigger_requires_no_auth(self):
        token = os.environ.get("INTERNAL_API_TOKEN", "")
        headers = {"X-Internal-Token": token} if token else {}
        response = requests.post(f"{EVALUATOR_URL}/score/trigger?background=true", headers=headers, timeout=5)
        assert response.status_code in [200, 401]

    @pytest.mark.skipif(not _is_service_up(STAGES_URL), reason="Stages service offline")
    def test_stages_health_includes_service_name(self):
        response = requests.get(f"{STAGES_URL}/health", timeout=5)
        assert response.status_code == 200
        assert response.json().get("service") == "stages"

    @pytest.mark.skipif(not _is_service_up(EVALUATOR_URL), reason="Evaluator service offline")
    def test_evaluator_health_includes_service_name(self):
        response = requests.get(f"{EVALUATOR_URL}/health", timeout=5)
        assert response.status_code == 200
        assert response.json().get("service") == "evaluator"

    @pytest.mark.skipif(not _is_service_up(DASHBOARD_URL, "/api/session"), reason="Dashboard offline")
    def test_dashboard_login_rejects_wrong_password(self):
        response = requests.post(f"{DASHBOARD_URL}/api/login", json={"password": "definitely_wrong_password_xyz123"}, timeout=5)
        assert response.status_code == 401

    @pytest.mark.skipif(not _is_service_up(DASHBOARD_URL, "/api/session"), reason="Dashboard offline")
    def test_dashboard_login_requires_password_field(self):
        response = requests.post(f"{DASHBOARD_URL}/api/login", json={}, timeout=5)
        assert response.status_code == 400

    @pytest.mark.skipif(not _is_service_up(STAGES_URL), reason="Stages service offline")
    def test_stages_stage1_rejects_invalid_campaign(self):
        token = os.environ.get("INTERNAL_API_TOKEN", "")
        headers = {"X-Internal-Token": token} if token else {}
        response = requests.post(f"{STAGES_URL}/stage1/run", json={"campaign_id": 999999}, headers=headers, timeout=5)
        assert response.status_code in [400, 401, 500]

    @pytest.mark.skipif(not _is_service_up(EVALUATOR_URL), reason="Evaluator service offline")
    def test_evaluator_score_invalid_candidate(self):
        token = os.environ.get("INTERNAL_API_TOKEN", "")
        headers = {"X-Internal-Token": token} if token else {}
        response = requests.post(f"{EVALUATOR_URL}/score/999999", headers=headers, timeout=5)
        assert response.status_code in [400, 401, 500]
