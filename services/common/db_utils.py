import uuid
import psycopg2.extras

_ALLOWED_CANDIDATE_COLUMNS = {
    "status", "score", "rationale", "company_name", "evidence_data", "notes",
    "contact_email", "contact_phone", "contact_name", "screenshot_url",
    "products_sold", "enrichment_report", "draft_email", "estimated_size",
    "estimated_revenue", "estimated_traffic", "enrichment_attempt_count",
    "duplicate_of_candidate_id", "processing_generation", "lease_id", "lease_expires_at",
    "source", "domain", "query_used", "created_at"
}

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
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]

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
