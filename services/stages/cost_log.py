"""
cost_log.py — helpers for writing to api_call_log (§0.6 cost/quota tracking).
Every paid API or LLM call in the system should call log_call().
"""
import json
from typing import Optional
import config
import db


def _estimate_cost(provider: str, tokens_in: int = 0, tokens_out: int = 0, query_count: int = 1) -> float:
    """Compute USD cost from the pricing map in config.py."""
    pricing = config.PRICING_MAP.get(provider, {})
    if "input_per_token" in pricing:
        return round(
            tokens_in * pricing["input_per_token"] + tokens_out * pricing["output_per_token"],
            6,
        )
    if "per_query" in pricing:
        return round(pricing["per_query"] * query_count, 6)
    return 0.0


def log_call(
    conn,
    stage: str,
    provider: str,
    *,
    campaign_id: Optional[int] = None,
    model: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    query_count: int = 1,
    cost_override: Optional[float] = None,
) -> None:
    """
    Insert one row into api_call_log.
    Call this immediately after every paid API/LLM call — before any error handling
    that might swallow the call, so partial failures are still recorded.
    """
    cost = cost_override if cost_override is not None else _estimate_cost(
        provider, tokens_in=tokens_in, tokens_out=tokens_out, query_count=query_count
    )
    db.execute(
        conn,
        """
        INSERT INTO api_call_log
            (campaign_id, stage, provider, model, tokens_in, tokens_out, query_count, cost_estimate_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (campaign_id, stage, provider, model, tokens_in or None, tokens_out or None, query_count, cost),
    )


def publicwww_budget_ok(conn, campaign_id: Optional[int] = None) -> bool:
    """
    Return True if PublicWWW spend this calendar month is under the monthly_quota.
    If no budget row exists, defaults to allowing the call (fail open).
    §Part 2: check before every PublicWWW batch, not after.
    """
    budget_row = db.fetchone(
        conn,
        "SELECT monthly_quota FROM provider_budgets WHERE provider = 'publicwww'",
    )
    if not budget_row or budget_row["monthly_quota"] is None:
        return True  # no budget configured — allow

    used_row = db.fetchone(
        conn,
        """
        SELECT COALESCE(SUM(query_count), 0) AS used
        FROM api_call_log
        WHERE provider = 'publicwww'
          AND date_trunc('month', created_at) = date_trunc('month', now())
        """,
    )
    used = int(used_row["used"]) if used_row else 0
    return used < budget_row["monthly_quota"]


def log_llm_parse_failure(conn, stage: str, model: str, campaign_id: Optional[int] = None) -> None:
    """
    Log an LLM JSON parse failure as a zero-cost sentinel row.
    This makes parse failures visible in the /api/usage cost dashboard
    under provider = 'llm_parse_failure'.
    """
    try:
        db.execute(
            conn,
            """
            INSERT INTO api_call_log
                (campaign_id, stage, provider, model, tokens_in, tokens_out, query_count, cost_estimate_usd)
            VALUES (%s, %s, 'llm_parse_failure', %s, 0, 0, 1, 0.0)
            """,
            (campaign_id, stage, model),
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("log_llm_parse_failure failed (non-fatal): %s", exc)

