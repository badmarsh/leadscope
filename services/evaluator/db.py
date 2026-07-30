"""
db.py — Thread-safe psycopg2 connection pool for the evaluator service.
Same pattern as services/stages/db.py.
"""
import time
import logging
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from contextlib import contextmanager

import services.common.config as config

logger = logging.getLogger(__name__)

_pool: pg_pool.ThreadedConnectionPool | None = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        retries = 10
        for i in range(retries):
            try:
                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=25,
                    dsn=config.DATABASE_URL,
                )
                break
            except psycopg2.OperationalError as e:
                if i < retries - 1:
                    logger.warning("Database connection failed (%s), retrying in 3 seconds...", str(e).strip())
                    time.sleep(3)
                else:
                    logger.error("Could not connect to database after %d retries.", retries)
                    raise
    return _pool


@contextmanager
def get_conn():
    conn = None
    retries = 5
    for attempt in range(retries):
        try:
            conn = get_pool().getconn()
            break
        except pg_pool.PoolError:
            if attempt < retries - 1:
                time.sleep(0.1)
            else:
                logger.error("Postgres connection pool exhausted after %d retries", retries)
                raise
    try:
        conn.autocommit = True
        yield conn
    finally:
        if conn:
            get_pool().putconn(conn)


def fetchone(conn, sql, params=()) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetchall(conn, sql, params=()) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def execute(conn, sql, params=()) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_returning(conn, sql, params=()) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


import logging

logger = logging.getLogger(__name__)

# Allowlist of valid stage identifiers — prevents f-string SQL injection
_VALID_STAGES = frozenset({"stage1", "stage2", "stage3", "stage5"})
_VALID_STATUSES = frozenset({"idle", "running", "stopping", "failed"})


def _validate_stage(stage: str) -> str:
    """Raise ValueError if stage is not in the allowlist."""
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid stage identifier: {stage!r}. Must be one of {sorted(_VALID_STAGES)}")
    return stage


def set_stage_status(campaign_id: int, stage: str, status: str):
    """
    Helper to update the pipeline status (and last_run) for a campaign.
    Requires its own temporary connection so statuses update instantly and survive rollbacks.
    Stage and status are validated against allowlists to prevent SQL injection.
    """
    _validate_stage(stage)  # allowlist check before f-string interpolation
    conn = get_pool().getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if status == "running":
                cur.execute(f"UPDATE campaigns SET {stage}_status = 'running' WHERE id = %s", (campaign_id,))
            elif status == "idle":
                cur.execute(
                    f"UPDATE campaigns SET {stage}_status = 'idle', {stage}_last_run = now() WHERE id = %s",
                    (campaign_id,),
                )
            elif status in _VALID_STATUSES:
                cur.execute(f"UPDATE campaigns SET {stage}_status = %s WHERE id = %s", (status, campaign_id))
            else:
                raise ValueError(f"Invalid status: {status!r}")
    except Exception as exc:
        logger.warning("set_stage_status failed (non-fatal): %s", exc)
    finally:
        get_pool().putconn(conn)


def acquire_stage_lock(campaign_id: int, stage: str) -> bool:
    """Atomic acquire: returns True only if we successfully transitioned idle→running."""
    _validate_stage(stage)
    conn = get_pool().getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE campaigns SET {stage}_status = 'running', "
                f"{stage}_last_run = NOW() "
                f"WHERE id = %s AND {stage}_status != 'running' "
                f"RETURNING id",
                (campaign_id,),
            )
            return cur.rowcount == 1
    except Exception as exc:
        logger.warning("acquire_stage_lock failed: %s", exc)
        return False
    finally:
        get_pool().putconn(conn)



def check_stop_signal(campaign_id: int, stage: str) -> bool:
    """
    Check if the stage status has been manually set to 'stopping'.
    Returns True if we should abort the run.
    Stage is validated against allowlist before f-string interpolation.
    """
    _validate_stage(stage)  # allowlist check
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT {stage}_status FROM campaigns WHERE id = %s", (campaign_id,))
            row = cur.fetchone()
            if not row:
                return False
            return row[f"{stage}_status"] == "stopping"

import uuid

def claim_candidates_for_stage(conn, campaign_id: int, from_statuses: list[str], to_status: str, limit: int = 50, order_by_source: bool = False):
    """
    Safely claims candidates using FOR UPDATE SKIP LOCKED.
    Updates processing_generation, lease_id, and lease_expires_at (15 mins).
    Returns list of candidate dicts with generation data.
    """
    lease_id = str(uuid.uuid4())
    order_clause = "ORDER BY (source = 'urlscan') DESC, created_at ASC" if order_by_source else "ORDER BY created_at ASC"
    
    # Format IN clause securely
    placeholders = ", ".join(["%s"] * len(from_statuses))
    params = list(from_statuses) + [campaign_id, limit, to_status, lease_id]
    
    sql = f"""
    WITH picked AS (
        SELECT id FROM candidates
        WHERE status IN ({placeholders}) AND campaign_id = %s
          AND (lease_expires_at IS NULL OR lease_expires_at < now())
        {order_clause}
        FOR UPDATE SKIP LOCKED
        LIMIT %s
    )
    UPDATE candidates c
    SET status = %s,
        lease_id = %s,
        lease_expires_at = now() + interval '15 minutes',
        processing_generation = processing_generation + 1
    FROM picked
    WHERE c.id = picked.id
    RETURNING c.*
    """
    return fetchall(conn, sql, tuple(params))

_ALLOWED_CANDIDATE_COLUMNS = {
    "status", "score", "rationale", "company_name", "evidence_data", "notes",
    "contact_email", "contact_phone", "contact_name", "screenshot_url",
    "products_sold", "enrichment_report", "draft_email", "estimated_size",
    "estimated_revenue", "estimated_traffic", "enrichment_attempt_count",
    "duplicate_of_candidate_id", "processing_generation", "lease_id", "lease_expires_at",
    "source", "domain", "query_used", "created_at"
}

def update_candidate_generation(conn, candidate_id: int, generation: int, updates: dict):
    """
    Updates a candidate ONLY if the processing_generation matches.
    Clears the lease upon update.
    Returns True if update succeeded, False if generation mismatched.
    Raises ValueError if an updates key is not in the column allowlist.
    """
    if not updates:
        return True
    
    set_clauses = []
    params = []
    for k, v in updates.items():
        if k not in _ALLOWED_CANDIDATE_COLUMNS:
            raise ValueError(f"Invalid column name for candidate update: {k!r}")
        set_clauses.append(f"{k} = %s")
        params.append(v)
    
    set_clauses.append("lease_id = NULL")
    set_clauses.append("lease_expires_at = NULL")
    
    sql = f"""
    UPDATE candidates
    SET {', '.join(set_clauses)}
    WHERE id = %s AND processing_generation = %s
    """
    params.extend([candidate_id, generation])
    
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.rowcount > 0
