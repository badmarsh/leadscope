-- =============================================================================
-- Part 1 validation script — run ALL checks, report results inline
-- =============================================================================

-- 1. Basic connectivity
SELECT 1 AS connectivity_check;

-- 2. Verify all tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- 3. Verify campaign rows were seeded correctly
SELECT slug, status, (business_brief IS NOT NULL) AS has_brief
FROM campaigns ORDER BY id;

-- 4. CHECK constraint: active campaign with NULL brief → should FAIL
DO $$
BEGIN
  BEGIN
    INSERT INTO campaigns (slug, name, finder_type, evaluator_type, business_brief, status)
    VALUES ('test-constraint-fail', 'Test', 'keyword_search', 'content_relevance', NULL, 'active');
    RAISE NOTICE 'FAIL: constraint did NOT fire as expected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'PASS: brief_required_unless_draft check constraint fires correctly';
  END;
END $$;

-- 5. FK constraint: bad campaign_id → should FAIL
DO $$
BEGIN
  BEGIN
    INSERT INTO candidates (campaign_id, domain) VALUES (9999, 'bad-fk-test.com');
    RAISE NOTICE 'FAIL: FK constraint did NOT fire as expected';
  EXCEPTION WHEN foreign_key_violation THEN
    RAISE NOTICE 'PASS: candidates FK constraint fires correctly on bad campaign_id';
  END;
END $$;

-- 6. Same domain under TWO different campaigns → should SUCCEED
INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'cross-campaign-test.com', 'new');
INSERT INTO candidates (campaign_id, domain, status) VALUES (2, 'cross-campaign-test.com', 'new');
SELECT 'PASS: same domain under two campaigns accepted' AS cross_campaign_test;

-- 7. Same domain under SAME campaign again → should FAIL (unique constraint)
DO $$
BEGIN
  BEGIN
    INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'cross-campaign-test.com', 'new');
    RAISE NOTICE 'FAIL: unique constraint did NOT fire as expected';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'PASS: UNIQUE(campaign_id, domain) fires correctly on duplicate';
  END;
END $$;

-- 8. status='stale' accepted
INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'stale-test.com', 'stale');
SELECT 'PASS: stale status accepted' AS stale_status_test;

-- 9. status='enrichment_failed' accepted
INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'enrichment-failed-test.com', 'enrichment_failed');
SELECT 'PASS: enrichment_failed status accepted' AS enrichment_failed_test;

-- 10. do_not_contact — campaign-specific
INSERT INTO do_not_contact (domain, campaign_id, reason)
VALUES ('dnc-specific.com', 1, 'Test campaign-specific suppress');
SELECT 'PASS: do_not_contact with campaign_id accepted' AS dnc_specific_test;

-- 11. do_not_contact — global (NULL campaign_id)
INSERT INTO do_not_contact (domain, campaign_id, reason)
VALUES ('dnc-global.com', NULL, 'Test global suppress');
SELECT 'PASS: do_not_contact with NULL campaign_id accepted' AS dnc_global_test;

-- 12. provider_budgets already has publicwww row; insert api_call_log referencing it
INSERT INTO api_call_log (campaign_id, stage, provider, model, tokens_in, tokens_out, cost_estimate_usd)
VALUES (1, 'stage1', 'gemini', 'gemini-2.5-flash', 1000, 250, 0.0003);
SELECT 'PASS: api_call_log row inserted with cost_estimate_usd' AS api_log_test;

-- 13. Check provider_budgets row exists
SELECT provider, monthly_quota, notes FROM provider_budgets;

-- 14. Final summary: row counts
SELECT
  (SELECT count(*) FROM campaigns) AS campaigns,
  (SELECT count(*) FROM candidates) AS candidates,
  (SELECT count(*) FROM do_not_contact) AS do_not_contact,
  (SELECT count(*) FROM api_call_log) AS api_call_log,
  (SELECT count(*) FROM provider_budgets) AS provider_budgets;

-- Clean up test rows
DELETE FROM candidates WHERE domain IN ('cross-campaign-test.com','stale-test.com','enrichment-failed-test.com');
DELETE FROM do_not_contact WHERE domain IN ('dnc-specific.com','dnc-global.com');
DELETE FROM api_call_log WHERE stage = 'stage1' AND provider = 'gemini' AND model = 'gemini-2.5-flash';
SELECT 'Cleanup done' AS cleanup;
