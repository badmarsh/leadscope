"""auth.py — Internal API token verification dependency."""
import os
import logging
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "").strip()
ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "development")).lower()


async def require_internal_token(x_internal_token: str = Header(default="")):
    """
    Verify X-Internal-Token header on internal microservice endpoints.
    Bypassed in development mode if INTERNAL_API_TOKEN is empty.
    Enforced in production mode.
    """
    token = os.getenv("INTERNAL_API_TOKEN", INTERNAL_API_TOKEN).strip()
    if not token:
        if ENVIRONMENT == "production":
            logger.error("Unauthorized API access attempt: INTERNAL_API_TOKEN is not configured in production")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Server authentication misconfigured",
            )
        return

    if x_internal_token.strip() != token:
        logger.warning("Unauthorized API access attempt: invalid X-Internal-Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Token header",
        )
