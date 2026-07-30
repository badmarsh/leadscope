import pytest
import os
import sys
from unittest.mock import patch
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import auth

@pytest.mark.asyncio
async def test_require_internal_token_valid():
    with patch.dict(os.environ, {"INTERNAL_API_TOKEN": "secret-token", "ENVIRONMENT": "production"}):
        # Should complete without raising HTTPException
        await auth.require_internal_token(x_internal_token="secret-token")

@pytest.mark.asyncio
async def test_require_internal_token_invalid():
    with patch.dict(os.environ, {"INTERNAL_API_TOKEN": "secret-token", "ENVIRONMENT": "production"}):
        with pytest.raises(HTTPException) as exc_info:
            await auth.require_internal_token(x_internal_token="wrong-token")
        assert exc_info.value.status_code == 401
        assert "Invalid or missing" in exc_info.value.detail

@pytest.mark.asyncio
async def test_require_internal_token_missing_in_production():
    with patch.dict(os.environ, {"INTERNAL_API_TOKEN": ""}), patch("auth.ENVIRONMENT", "production"):
        with pytest.raises(HTTPException) as exc_info:
            await auth.require_internal_token(x_internal_token="")
        assert exc_info.value.status_code == 401
        assert "misconfigured" in exc_info.value.detail

@pytest.mark.asyncio
async def test_require_internal_token_missing_in_development():
    with patch.dict(os.environ, {"INTERNAL_API_TOKEN": "", "ENVIRONMENT": "development"}):
        # Should allow in dev mode
        await auth.require_internal_token(x_internal_token="")
