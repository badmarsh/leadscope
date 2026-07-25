"""
main.py — Evaluator service: FastAPI app with scoring endpoints.

Part 3 implementation: three pluggable scorer strategies behind a shared harness,
keyed by campaigns.evaluator_type (content_relevance, image_quality, threat_intel).
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends

import services.common.config as config
import harness
from auth import require_internal_token

log_dir = "/var/log/app"
try:
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")
    # Test file writeability
    with open(log_file, "a") as f:
        pass
except (OSError, PermissionError):
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log active model configuration at startup (after logging is fully initialised)."""
    logger.info(
        "Evaluator ready | SCORER_VISION_MODEL=%s | SCORER_TEXT_MODEL=%s | PROXY=%s",
        config.SCORER_VISION_MODEL,
        config.SCORER_TEXT_MODEL,
        config.GEMINI_PROXY_ENDPOINT,
    )
    yield


app = FastAPI(title="Leadscope Evaluator", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "evaluator", "version": "1.0.0"}


# IMPORTANT: /score/trigger MUST be defined before /score/{candidate_id}
# otherwise FastAPI matches "trigger" as candidate_id.
@app.post("/score/trigger", dependencies=[Depends(require_internal_token)])
def trigger_scoring(background_tasks: BackgroundTasks, background: bool = False):
    """
    Poll for candidates with status='new', score each, flip to 'pending_review'.
    """
    try:
        if background:
            background_tasks.add_task(harness.trigger_scoring)
            return {"ok": True, "message": "Scoring started in background"}
        else:
            result = harness.trigger_scoring()
            return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("Scoring trigger failed")
        raise HTTPException(status_code=500, detail="Trigger failed")


@app.post("/score/{candidate_id}", dependencies=[Depends(require_internal_token)])
def score_candidate(candidate_id: int):
    """
    Score a single candidate through the evaluator harness.
    Routes to the correct scorer based on campaigns.evaluator_type.
    """
    try:
        result = harness.score_candidate(candidate_id)
        return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Candidate scoring failed for ID %s", candidate_id)
        raise HTTPException(status_code=500, detail="Scoring failed")
