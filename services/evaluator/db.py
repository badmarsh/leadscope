"""
db.py — Thread-safe psycopg2 connection pool for the evaluator service.
Same pattern as services/stages/db.py.
"""
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from contextlib import contextmanager

import config

_pool: pg_pool.ThreadedConnectionPool | None = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=config.DATABASE_URL,
        )
    return _pool


@contextmanager
def get_conn():
    conn = get_pool().getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
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


def _validate_stage(stage: str) -> str:
    """Raise ValueError if stage is not in the allowlist."""
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid stage identifier: {stage!r}. Must be one of {sorted(_VALID_STAGES)}")
    return stage


def set_stage_status(campaign_id: int, stage: str, status: str):
    """
    Helper to update the pipeline status (and last_run) for a campaign.
    Requires its own temporary connection so statuses update instantly and survive rollbacks.
    Stage is validated against allowlist to prevent SQL injection.
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
            else:
                cur.execute(f"UPDATE campaigns SET {stage}_status = %s WHERE id = %s", (status, campaign_id))
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
