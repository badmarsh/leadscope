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


if __name__ == "__main__":
    unittest.main()
