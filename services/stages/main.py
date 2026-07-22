"""
main.py — FastAPI app for the stages service.
Exposes HTTP endpoints for Stages 1, 2, and 5, callable from n8n workflows
or manually during validation.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

import db
import stage1
import stage2
import stage5
import kb_ingest

log_dir = "/var/log/app"
try:
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")
    with open(log_file, "a") as f:
        pass
except (OSError, PermissionError):
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: reset any stages stuck in running/stopping due to a previous crash (H6)."""
    logger.info("Stages service starting up — checking for stuck pipeline statuses...")
    db.reset_stuck_statuses()
    yield
    logger.info("Stages service shutting down.")


app = FastAPI(title="Leadscope Stages Service", version="1.0.0", lifespan=lifespan)


class CampaignRequest(BaseModel):
    campaign_id: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "stages"}


# ── Stage 1: ICP Definer ───────────────────────────────────────────────────────

@app.post("/stage1/run")
def run_stage1(req: CampaignRequest, background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Stage 1 (Brief/ICP Definer) for a specific campaign.
    Refuses if campaign.status = 'draft'.
    """
    try:
        if background:
            background_tasks.add_task(stage1.run, req.campaign_id)
            return {"ok": True, "message": "Stage 1 started in background"}
        else:
            result = stage1.run(req.campaign_id)
            return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage 1 failed: {exc}")


# ── Stage 2: Target Finder ────────────────────────────────────────────────────

@app.post("/stage2/run")
def run_stage2(req: CampaignRequest, background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Stage 2 (Target Finder) for a specific campaign.
    Routes on campaigns.finder_type (keyword_search or code_signature_search).
    """
    try:
        if background:
            background_tasks.add_task(stage2.run, req.campaign_id)
            return {"ok": True, "message": "Stage 2 started in background"}
        else:
            result = stage2.run(req.campaign_id)
            return {"ok": True, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage 2 failed: {exc}")


@app.post("/stage2/run-all")
def run_stage2_all(background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Stage 2 for ALL active campaigns.
    """
    try:
        if background:
            background_tasks.add_task(stage2.run_all)
            return {"ok": True, "message": "Stage 2 run-all started in background"}
        else:
            results = stage2.run_all()
            return {"ok": True, "results": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage 2 run-all failed: {exc}")


# ── Stage 5: Enrichment ────────────────────────────────────────────────────────

@app.post("/stage5/run")
def run_stage5(background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Stage 5 (Enrichment) — polls all approved candidates.
    """
    try:
        if background:
            background_tasks.add_task(stage5.run)
            return {"ok": True, "message": "Stage 5 started in background"}
        else:
            result = stage5.run()
            return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage 5 failed: {exc}")

# ── Knowledge Base Ingestion ────────────────────────────────────────────────────

@app.post("/kb/ingest")
def run_kb_ingest(background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Knowledge Base ingestion — scrapes Wordfence RSS and extracts malware signatures.
    """
    try:
        if background:
            background_tasks.add_task(kb_ingest.run)
            return {"ok": True, "message": "KB Ingestion started in background"}
        else:
            result = kb_ingest.run()
            return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KB Ingestion failed: {exc}")
