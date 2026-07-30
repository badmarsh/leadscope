"""
db.py — thread-safe psycopg2 connection pool for the stages service.
Uses a ThreadedConnectionPool so multiple FastAPI threads share connections.

NOTE: get_conn() sets autocommit = True. Multi-statement transactions require raw psycopg2 connections or manual transaction management (conn.autocommit = False).
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

# Allowlist of valid stage identifiers — prevents f-string SQL injection (C1)
_VALID_STAGES = frozenset({"stage1", "stage2", "stage3", "stage5"})
_VALID_STATUSES = frozenset({"idle", "running", "stopping", "failed"})


def _validate_stage(stage: str) -> str:
    """Raise ValueError if stage is not in the allowlist."""
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid stage identifier: {stage!r}. Must be one of {sorted(_VALID_STAGES)}")
    return stage


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
def get_conn(autocommit: bool = True):
    """Context manager that checks out a connection with retry on pool exhaustion."""
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
        conn.autocommit = autocommit
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit and conn:
            conn.rollback()
        raise
    finally:
        if conn:
            get_pool().putconn(conn)


def fetchone(conn, sql: str, params=()) -> dict | None:
    """Execute a SELECT and return the first row as a dict (or None)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetchall(conn, sql: str, params=()) -> list[dict]:
    """Execute a SELECT and return all rows as dicts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def execute(conn, sql: str, params=()) -> int:
    """Execute a DML statement and return rowcount."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_returning(conn, sql: str, params=()) -> dict | None:
    """Execute a DML statement with RETURNING and return the first row."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def set_stage_status(campaign_id: int, stage: str, status: str):
    """
    Helper to update the pipeline status (and last_run) for a campaign.
    Requires its own temporary connection so statuses update instantly and survive rollbacks.
    Stage and status are validated against allowlists to prevent SQL injection (C1).
    """
    _validate_stage(stage)  # C1: allowlist check before f-string interpolation

    conn = get_pool().getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if status == "running":
                cur.execute(
                    f"UPDATE campaigns SET {stage}_status = 'running' WHERE id = %s",
                    (campaign_id,),
                )
            elif status == "idle":
                cur.execute(
                    f"UPDATE campaigns SET {stage}_status = 'idle', {stage}_last_run = now() WHERE id = %s",
                    (campaign_id,),
                )
            elif status in _VALID_STATUSES:
                cur.execute(
                    f"UPDATE campaigns SET {stage}_status = %s WHERE id = %s",
                    (status, campaign_id),
                )
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
            cur.execute("SELECT id FROM campaigns WHERE id = %s", (campaign_id,))
            if not cur.fetchone():
                raise ValueError(f"Campaign {campaign_id} not found")

            cur.execute(
                f"UPDATE campaigns SET {stage}_status = 'running', "
                f"{stage}_last_run = NOW() "
                f"WHERE id = %s AND {stage}_status != 'running' "
                f"RETURNING id",
                (campaign_id,),
            )
            return cur.rowcount == 1
    except Exception as exc:
        logger.warning("acquire_stage_lock failed transiently: %s", exc)
        raise exc
    finally:
        get_pool().putconn(conn)



def check_stop_signal(campaign_id: int, stage: str) -> bool:
    """
    Check if the stage status has been manually set to 'stopping'.
    Returns True if we should abort the run.
    Stage is validated against allowlist before f-string interpolation (C1).
    """
    _validate_stage(stage)  # C1: allowlist check

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT {stage}_status FROM campaigns WHERE id = %s",
                (campaign_id,),
            )
            row = cur.fetchone()
            if not row:
                return False
            return row[f"{stage}_status"] == "stopping"


def reset_stuck_statuses():
    """
    On service startup, reset any stages stuck in 'running' or 'stopping' back to 'idle'.
    This handles the case where the service crashed mid-run (H6).
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE campaigns SET
                        stage1_status = CASE WHEN stage1_status IN ('running', 'stopping') THEN 'idle' ELSE stage1_status END,
                        stage2_status = CASE WHEN stage2_status IN ('running', 'stopping') THEN 'idle' ELSE stage2_status END,
                        stage3_status = CASE WHEN stage3_status IN ('running', 'stopping') THEN 'idle' ELSE stage3_status END,
                        stage5_status = CASE WHEN stage5_status IN ('running', 'stopping') THEN 'idle' ELSE stage5_status END
                    WHERE stage1_status IN ('running', 'stopping')
                       OR stage2_status IN ('running', 'stopping')
                       OR stage3_status IN ('running', 'stopping')
                       OR stage5_status IN ('running', 'stopping')
                """)
                count = cur.rowcount
                if count > 0:
                    logger.warning(
                        "Startup recovery: reset %d campaign(s) with stuck 'running'/'stopping' statuses to 'idle'",
                        count,
                    )
    except Exception as exc:
        logger.error("reset_stuck_statuses failed: %s", exc)
