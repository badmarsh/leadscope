import pytest
import psycopg2
import os
import threading
import time
from services.common.db_utils import update_candidate_generation, claim_candidates_for_stage

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope_test:leadscope_test@localhost:5432/leadscope_test")

@pytest.fixture
def conn():
    c = psycopg2.connect(DATABASE_URL)
    c.autocommit = True
    yield c
    c.close()

@pytest.fixture
def setup_candidate(conn):
    with conn.cursor() as cur:
        # Create a campaign
        cur.execute("INSERT INTO campaigns (name, slug, business_brief, finder_type, evaluator_type) VALUES ('Test Camp', 'test-camp-ci', 'Brief', 'keyword_search', 'content_relevance') RETURNING id")
        camp_id = cur.fetchone()[0]
        # Insert a candidate
        cur.execute("INSERT INTO candidates (campaign_id, domain, status, processing_generation) VALUES (%s, 'testlock.com', 'new', 0) RETURNING id", (camp_id,))
        cand_id = cur.fetchone()[0]
    yield camp_id, cand_id
    with conn.cursor() as cur:
        cur.execute("DELETE FROM candidates WHERE campaign_id = %s", (camp_id,))
        cur.execute("DELETE FROM campaigns WHERE id = %s", (camp_id,))

def test_update_candidate_generation_success(conn, setup_candidate):
    camp_id, cand_id = setup_candidate
    
    # Matching generation should succeed
    success = update_candidate_generation(conn, cand_id, 0, {"status": "evaluating"})
    assert success is True
    
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM candidates WHERE id = %s", (cand_id,))
        assert cur.fetchone()[0] == "evaluating"

def test_update_candidate_generation_mismatch(conn, setup_candidate):
    camp_id, cand_id = setup_candidate
    
    # Mismatch generation should fail and not update
    success = update_candidate_generation(conn, cand_id, 999, {"status": "discarded"})
    assert success is False
    
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM candidates WHERE id = %s", (cand_id,))
        assert cur.fetchone()[0] == "new"

def test_claim_candidates_for_stage(conn, setup_candidate):
    camp_id, cand_id = setup_candidate
    
    # Should successfully claim and increment generation
    claimed = claim_candidates_for_stage(conn, camp_id, ["new"], "evaluating")
    assert len(claimed) == 1
    assert claimed[0]["id"] == cand_id
    assert claimed[0]["processing_generation"] == 1
    assert claimed[0]["lease_id"] is not None
    
    # Second claim should return empty
    claimed2 = claim_candidates_for_stage(conn, camp_id, ["new"], "evaluating")
    assert len(claimed2) == 0

def test_claim_candidates_skip_locked(setup_candidate):
    camp_id, cand_id = setup_candidate
    
    # Thread 1 locks the candidate
    conn1 = psycopg2.connect(DATABASE_URL)
    conn1.autocommit = False
    
    conn2 = psycopg2.connect(DATABASE_URL)
    conn2.autocommit = True
    
    try:
        cur1 = conn1.cursor()
        cur1.execute("SELECT id FROM candidates WHERE id = %s FOR UPDATE", (cand_id,))
        
        # Thread 2 tries to claim
        claimed = claim_candidates_for_stage(conn2, camp_id, ["new"], "evaluating")
        assert len(claimed) == 0 # Skipped because it's locked by conn1!
        
        conn1.rollback()
    finally:
        conn1.close()
        conn2.close()
