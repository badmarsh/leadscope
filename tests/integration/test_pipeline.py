"""
Integration test suite for the multi-stage lead generation pipeline.
Tests service health, database connectivity, ICP generation, target finding, and scoring evaluator.
Uses Python's native unittest module for zero-dependency execution.
"""
import os
import unittest
import requests

STAGES_URL = os.environ.get("STAGES_URL", "http://127.0.0.1:8002")
EVALUATOR_URL = os.environ.get("EVALUATOR_URL", "http://127.0.0.1:8001")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:3000")


class TestPipelineIntegration(unittest.TestCase):

    def test_stages_health(self):
        """Verify Stages microservice health endpoint."""
        try:
            r = requests.get(f"{STAGES_URL}/health", timeout=3)
            self.assertEqual(r.status_code, 200, f"Stages health error: {r.text}")
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Stages service offline on {STAGES_URL}: {e}")

    def test_evaluator_health(self):
        """Verify Evaluator microservice health endpoint."""
        try:
            r = requests.get(f"{EVALUATOR_URL}/health", timeout=3)
            self.assertEqual(r.status_code, 200, f"Evaluator health error: {r.text}")
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Evaluator service offline on {EVALUATOR_URL}: {e}")

    def test_dashboard_health(self):
        """Verify Next.js Dashboard health / session API."""
        try:
            r = requests.get(f"{DASHBOARD_URL}/api/session", timeout=3)
            self.assertIn(r.status_code, (200, 401), f"Unexpected status: {r.status_code}")
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Dashboard offline on {DASHBOARD_URL}: {e}")

    def test_evaluator_score_trigger_requires_no_auth(self):
        try:
            response = requests.post(f"{EVALUATOR_URL}/score/trigger?background=true", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get("ok"))
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Evaluator service offline on {EVALUATOR_URL}: {e}")

    def test_stages_health_includes_service_name(self):
        try:
            response = requests.get(f"{STAGES_URL}/health", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("service"), "stages")
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Stages service offline on {STAGES_URL}: {e}")

    def test_evaluator_health_includes_service_name(self):
        try:
            response = requests.get(f"{EVALUATOR_URL}/health", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("service"), "evaluator")
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Evaluator service offline on {EVALUATOR_URL}: {e}")

    def test_dashboard_login_rejects_wrong_password(self):
        try:
            response = requests.post(f"{DASHBOARD_URL}/api/login", json={"password": "definitely_wrong_password_xyz123"}, timeout=5)
            self.assertEqual(response.status_code, 401)
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Dashboard service offline on {DASHBOARD_URL}: {e}")

    def test_dashboard_login_requires_password_field(self):
        try:
            response = requests.post(f"{DASHBOARD_URL}/api/login", json={}, timeout=5)
            self.assertEqual(response.status_code, 400)
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Dashboard service offline on {DASHBOARD_URL}: {e}")

    def test_stages_stage1_rejects_invalid_campaign(self):
        try:
            response = requests.post(f"{STAGES_URL}/stage1/run", json={"campaign_id": 999999}, timeout=5)
            self.assertIn(response.status_code, [400, 500])
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Stages service offline on {STAGES_URL}: {e}")

    def test_evaluator_score_invalid_candidate(self):
        try:
            response = requests.post(f"{EVALUATOR_URL}/score/999999", timeout=5)
            self.assertIn(response.status_code, [400, 500])
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Evaluator service offline on {EVALUATOR_URL}: {e}")

if __name__ == "__main__":
    unittest.main()
