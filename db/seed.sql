-- =============================================================================
-- Part 1 — Seed data & constraint validation
-- =============================================================================

-- -----------------------------------------------------------------------
-- 1. Seed the three campaign rows
-- -----------------------------------------------------------------------

-- Campaign 1: JENEX HVAC (Hungary) — status='active', full brief
INSERT INTO campaigns (slug, name, finder_type, evaluator_type, business_brief, reference_materials, status)
VALUES (
  'jenex-hu-hvac',
  'JENEX HVAC Hungary',
  'keyword_search',
  'content_relevance',
  'JENEX Dobšiná, s.r.o. (Kúpeľná 983, Dobšiná 049 25, Slovakia; founded 1997; Director: Ing. Tibor Jedinák; sales: obchod@jenexsro.sk) manufactures and sells SWAH corner brackets — patented, galvanized-steel corner connectors for SWAH-type ventilation duct profiles. Products in scope: 20SH (standard, order no. 400 100 020, 300 pcs/box), 20LSH (extended, order no. 400 100 021, 300 pcs/box), 30SH (larger profile, order no. 400 100 030, 300 pcs/box). Target customer types: HVAC wholesalers and distributors, ductwork fabricators, HVAC construction and projektant firms. Geographic focus: Hungary (HU market). JENEX already publishes jenexsro.sk/hu/ indicating existing HU-market intent. Reference catalogs: https://www.jenexsro.sk/en/product-catalog/ and the 2022/2024 PDF catalogs.',
  '{"catalogs": ["https://www.jenexsro.sk/en/product-catalog/", "https://www.jenexsro.sk/wp-content/uploads/2022/11/Jenex-2022-en.pdf", "https://www.jenexsro.sk/wp-content/uploads/2024/10/JENEX-PROFESSIONAL-QUALITY-VENTILATION-2024.pdf"], "hu_site": "https://www.jenexsro.sk/hu/"}'::jsonb,
  'active'
);

-- Campaign 2: Shoe-photo-upgrade — status='draft', business_brief NULL (not yet filled in)
INSERT INTO campaigns (slug, name, finder_type, evaluator_type, business_brief, reference_materials, status)
VALUES (
  'shoe-photo-upgrade',
  'Shoe Photo Upgrade',
  'keyword_search',
  'image_quality',
  NULL,  -- brief not filled in yet — see §0.3
  NULL,
  'draft'
);

-- Campaign 3: WP-remediation — status='draft', business_brief NULL (not yet filled in)
-- Note: Part 5 (signature ingestion) does NOT need this brief and can run immediately.
INSERT INTO campaigns (slug, name, finder_type, evaluator_type, business_brief, reference_materials, status)
VALUES (
  'wp-remediation',
  'WP Remediation',
  'code_signature_search',
  'threat_intel',
  NULL,  -- brief not filled in yet — see §0.3
  NULL,
  'draft'
);

-- -----------------------------------------------------------------------
-- 2. Seed provider_budgets
-- -----------------------------------------------------------------------
-- PublicWWW: quota is query count per month (update with your real account limit)
INSERT INTO provider_budgets (provider, monthly_quota, notes)
VALUES (
  'publicwww',
  500,  -- placeholder; replace with your actual PublicWWW account monthly query limit
  'Query count per calendar month. Check account tier at publicwww.com.'
);

-- -----------------------------------------------------------------------
-- 3. Constraint validation queries (run these manually to verify)
-- -----------------------------------------------------------------------

-- 3a. Verify brief_required_unless_draft check constraint:
--     This should FAIL (active campaign with NULL brief):
-- INSERT INTO campaigns (slug, name, finder_type, evaluator_type, business_brief, status)
-- VALUES ('test-fail', 'Test Fail', 'keyword_search', 'content_relevance', NULL, 'active');
-- Expected error: new row for relation "campaigns" violates check constraint "brief_required_unless_draft"

-- 3b. FK constraint test — should FAIL (bad campaign_id = 9999):
-- INSERT INTO candidates (campaign_id, domain) VALUES (9999, 'bad-fk-test.com');

-- 3c. UNIQUE(campaign_id, domain) tests:
--     Same domain under TWO different campaigns — should SUCCEED:
-- INSERT INTO candidates (campaign_id, domain) VALUES (1, 'cross-campaign-test.com');
-- INSERT INTO candidates (campaign_id, domain) VALUES (2, 'cross-campaign-test.com');
--     Same domain under SAME campaign — should FAIL:
-- INSERT INTO candidates (campaign_id, domain) VALUES (1, 'cross-campaign-test.com');

-- 3d. Accepted status values (stale, enrichment_failed):
-- INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'stale-test.com', 'stale');
-- INSERT INTO candidates (campaign_id, domain, status) VALUES (1, 'enrichment-failed-test.com', 'enrichment_failed');

-- 3e. do_not_contact — with campaign_id and with NULL (global):
-- INSERT INTO do_not_contact (domain, campaign_id, reason) VALUES ('dnc-specific.com', 1, 'Test specific suppress');
-- INSERT INTO do_not_contact (domain, campaign_id, reason) VALUES ('dnc-global.com', NULL, 'Test global suppress');

-- 3f. api_call_log referencing provider_budgets:
-- INSERT INTO api_call_log (campaign_id, stage, provider, model, tokens_in, tokens_out, cost_estimate_usd)
-- VALUES (1, 'stage1', 'gemini', 'gemini-2.5-flash', 1000, 250, 0.0003);
