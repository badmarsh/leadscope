"""
main.py — FastAPI app for the stages service.
Exposes HTTP endpoints for Stages 1, 2, and 5, callable from n8n workflows
or manually during validation.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel

import db
import stage1
import stage2
import stage4
import stage5
import kb_ingest
from auth import require_internal_token
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from watchdog import check_stuck_stages

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
    force=True,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: reset stuck pipeline statuses, then start a 30-minute watchdog."""
    logger.info("Stages service starting up — checking for stuck pipeline statuses...")
    db.reset_stuck_statuses()
    check_stuck_stages()

    # Periodic watchdog — alerts on stages stuck longer than WATCHDOG_TIMEOUT_MINUTES
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_stuck_stages, "interval", minutes=30, id="watchdog")
    scheduler.start()
    logger.info("Watchdog scheduler started — will check for stuck stages every 30 minutes")

    yield

    scheduler.shutdown(wait=False)
    logger.info("Stages service shutting down.")


app = FastAPI(title="Leadscope Stages Service", version="1.0.0", lifespan=lifespan)


class CampaignRequest(BaseModel):
    campaign_id: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "stages"}


# ── Stage 1: ICP Definer ───────────────────────────────────────────────────────

@app.post("/stage1/run", dependencies=[Depends(require_internal_token)])
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
        logger.exception("Stage 1 execution failed")
        raise HTTPException(status_code=500, detail="Stage 1 processing failed")


# ── Stage 2: Target Finder ────────────────────────────────────────────────────

@app.post("/stage2/run", dependencies=[Depends(require_internal_token)])
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
        logger.exception("Stage 2 execution failed")
        raise HTTPException(status_code=500, detail="Stage 2 processing failed")


@app.post("/stage2/run-all", dependencies=[Depends(require_internal_token)])
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
        logger.exception("Stage 2 run-all execution failed")
        raise HTTPException(status_code=500, detail="Stage 2 run-all processing failed")


# ── Stage 4: Contact Discovery ────────────────────────────────────────────────

@app.post("/stage4/run", dependencies=[Depends(require_internal_token)])
def run_stage4(background_tasks: BackgroundTasks, background: bool = False):
    """
    Run Stage 4 (Contact Discovery) — polls approved candidates for contacts.
    """
    try:
        if background:
            background_tasks.add_task(stage4.run)
            return {"ok": True, "message": "Stage 4 started in background"}
        else:
            result = stage4.run()
            return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("Stage 4 execution failed")
        raise HTTPException(status_code=500, detail="Stage 4 processing failed")


# ── Stage 5: Enrichment ────────────────────────────────────────────────────────

@app.post("/stage5/run", dependencies=[Depends(require_internal_token)])
def run_stage5(req: Optional[CampaignRequest] = None, background_tasks: BackgroundTasks = None, background: bool = False):
    """
    Run Stage 5 (Enrichment) — polls all approved candidates, optionally filtered by campaign.
    """
    try:
        camp_id = req.campaign_id if req else None
        if background:
            background_tasks.add_task(stage5.run, camp_id)
            return {"ok": True, "message": "Stage 5 started in background"}
        else:
            result = stage5.run(camp_id)
            return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("Stage 5 execution failed")
        raise HTTPException(status_code=500, detail="Stage 5 processing failed")

# ── Knowledge Base Ingestion ────────────────────────────────────────────────────

@app.post("/kb/ingest", dependencies=[Depends(require_internal_token)])
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
        logger.exception("KB ingestion failed")
        raise HTTPException(status_code=500, detail="KB Ingestion processing failed")
