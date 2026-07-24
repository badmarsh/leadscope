# conftest.py — repo root
# This file provides global fixtures.
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

import pytest
from unittest.mock import MagicMock, patch

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
