# conftest.py — repo root
# This file provides global fixtures.
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Ensure local service paths take precedence over installed packages (e.g. email_validator)
repo_root = os.path.dirname(os.path.abspath(__file__))
service_paths = [
    os.path.join(repo_root, "services", "stages"),
    os.path.join(repo_root, "services", "evaluator"),
    os.path.join(repo_root, "services", "crawler"),
    os.path.join(repo_root, "services", "jobs"),
]
for p in service_paths:
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

@pytest.fixture
def mock_env():
    """Provides a standard set of mock environment variables for testing."""
    env = {
        "DATABASE_URL": "postgresql://mock:mock@localhost/mock",
        "EVALUATOR_URL": "http://evaluator:8001",
        "STAGES_URL": "http://stages:8002",
        "DASHBOARD_URL": "http://dashboard:3000",
        "OPENAI_API_KEY": "sk-mock",
        "ANTHROPIC_API_KEY": "sk-mock"
    }
    with patch.dict(os.environ, env, clear=False):
        yield env

@pytest.fixture
def mock_db_conn():
    """Provides a MagicMock database connection commonly used in tests."""
    return MagicMock()
