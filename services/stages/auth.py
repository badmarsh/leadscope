"""auth.py — Internal API token verification dependency."""
import os
import logging
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")


async def require_internal_token(x_internal_token: str = Header(default="")):
    """
    Verify X-Internal-Token header on internal microservice endpoints.
    Bypassed if INTERNAL_API_TOKEN is empty string (default for local dev).
    """
    if INTERNAL_API_TOKEN and x_internal_token != INTERNAL_API_TOKEN:
        logger.warning("Unauthorized API access attempt: invalid X-Internal-Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Token header",
        )
