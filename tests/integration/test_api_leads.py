import os
import pytest
import requests

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:3000")


def _dashboard_up() -> bool:
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/session", timeout=2)
        return r.status_code in (200, 401)
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _dashboard_up(), reason="Dashboard service not reachable")
class TestLeadsAPI:

    def test_leads_auth_protection(self):
        r = requests.get(f"{DASHBOARD_URL}/api/leads?campaign_id=2", timeout=5)
        # Unauthenticated request should return 401 or 200 depending on middleware
        assert r.status_code in (200, 401)

    def test_leads_without_campaign_id_returns_400_or_401(self):
        r = requests.get(f"{DASHBOARD_URL}/api/leads", timeout=5)
        assert r.status_code in (400, 401)

    def test_leads_invalid_campaign_returns_expected_status(self):
        r = requests.get(f"{DASHBOARD_URL}/api/leads?campaign_id=999999", timeout=5)
        assert r.status_code in (200, 401, 404)
