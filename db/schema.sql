-- =============================================================================
-- Part 1 — Full database schema
-- Multi-vertical lead-generation platform
-- =============================================================================

CREATE TABLE campaigns (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,             -- 'jenex-hu-hvac', 'shoe-photo-upgrade', 'wp-remediation'
  name TEXT NOT NULL,
  finder_type TEXT NOT NULL,             -- 'keyword_search' | 'code_signature_search'
  evaluator_type TEXT NOT NULL,          -- 'content_relevance' | 'image_quality' | 'threat_intel'
  business_brief TEXT,                   -- nullable; use status='draft' to gate placeholder briefs
  reference_materials JSONB,
  status TEXT DEFAULT 'active',          -- active | paused | draft
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  settings JSONB NOT NULL DEFAULT '{}',
  stage1_status TEXT DEFAULT 'idle',
  stage1_last_run TIMESTAMPTZ,
  stage2_status TEXT DEFAULT 'idle',
  stage2_last_run TIMESTAMPTZ,
  stage3_status TEXT DEFAULT 'idle',
  stage3_last_run TIMESTAMPTZ,
  stage5_status TEXT DEFAULT 'idle',
  stage5_last_run TIMESTAMPTZ,
  CONSTRAINT brief_required_unless_draft
    CHECK (status = 'draft' OR business_brief IS NOT NULL)
);

CREATE TABLE icp_config (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  version INT NOT NULL,
  target_segments JSONB NOT NULL,
  keywords_hu TEXT[],
  keywords_en TEXT[],
  disqualifiers JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE malware_signatures (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  snippet TEXT NOT NULL,
  malware_family TEXT,
  source_url TEXT CHECK (source_url IS NULL OR source_url LIKE 'http%'),
  confidence TEXT DEFAULT 'medium',      -- low | medium | high
  added_at TIMESTAMPTZ DEFAULT now(),
  sneakiness_tier TEXT DEFAULT 'C',
  proof_method TEXT DEFAULT NULL,
  outreach_hook TEXT DEFAULT NULL,
  outbreak_scope TEXT DEFAULT 'global',
  UNIQUE(campaign_id, snippet)
);

CREATE TABLE candidates (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  company_name TEXT,
  domain TEXT NOT NULL,
  source TEXT,
  query_used TEXT,
  evidence_data JSONB,                    -- discovery-time evidence (e.g. which signature(s) matched)
  status TEXT DEFAULT 'new',              -- new | evaluated | pending_review | approved | rejected | enriched | stale | enrichment_failed
  enrichment_attempted_at TIMESTAMPTZ,     -- tracks Stage 5 attempts so Firecrawl failures don't loop silently
  enrichment_attempt_count INT DEFAULT 0,  -- caps retries (Part 2, Stage 5) — see MAX_ENRICHMENT_ATTEMPTS
  evaluated_at TIMESTAMPTZ,                -- tracks when Stage 3 / find_malware completed domain evaluation
  last_seen_at TIMESTAMPTZ DEFAULT now(),  -- bumped whenever Stage 2 re-encounters this domain
  reopen_count INT DEFAULT 0,              -- how many times a stale candidate got reopened by rediscovery
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  audit_token TEXT UNIQUE DEFAULT NULL,
  audit_token_created TIMESTAMPTZ DEFAULT NULL,
  audit_viewed_at TIMESTAMPTZ DEFAULT NULL,
  audit_view_count INT DEFAULT 0,
  processing_generation BIGINT NOT NULL DEFAULT 0,
  lease_id UUID,
  lease_expires_at TIMESTAMPTZ,
  UNIQUE(campaign_id, domain)
);

CREATE TABLE do_not_contact (
  id SERIAL PRIMARY KEY,
  domain TEXT NOT NULL,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,  -- NULL = suppress this domain across every campaign
  reason TEXT,
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(domain, campaign_id)
);

CREATE TABLE evaluations (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE,
  score INT,                              -- 0-100, always "how good an opportunity this is"
  rationale TEXT,
  evidence_urls TEXT[],
  evidence_data JSONB,                    -- vertical-specific structured evidence
  model_used TEXT,
  icp_version_used INT,                   -- records which icp_config.version this score was computed against
  status TEXT DEFAULT 'pending_review',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feedback (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE,
  decision TEXT NOT NULL,                 -- approved | rejected
  note TEXT,
  reviewed_by TEXT,                       -- single permanent operator: leave free-text/nullable, no user model needed
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE UNIQUE,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,  -- denormalized for direct per-campaign dashboard queries without a join through candidates
  contact_email TEXT,
  contact_phone TEXT,
  contact_name TEXT,
  draft_email TEXT,
  screenshot_url TEXT,
  products_sold TEXT[],
  enrichment_report TEXT,
  estimated_size TEXT,
  estimated_revenue TEXT,
  estimated_traffic TEXT,
  firmographics JSONB,
  buying_power_signals TEXT[],
  tech_stack TEXT[],
  cold_email_hook TEXT,
  mx_valid BOOLEAN DEFAULT NULL,
  enriched_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_call_log (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,   -- nullable: some calls (e.g. signature ingestion) aren't cleanly one campaign's spend
  stage TEXT NOT NULL,                    -- 'stage1' | 'stage2' | 'stage3' | 'stage5' | 'signature_ingestion' | 'reverification'
  provider TEXT NOT NULL,                 -- 'gemini' | 'openrouter' | 'ollama' | 'exa' | 'tavily' | 'serper' | 'serpapi' | 'brave' | 'publicwww' | 'firecrawl'
  model TEXT,                             -- NULL for non-LLM providers
  tokens_in INT,
  tokens_out INT,
  query_count INT DEFAULT 1,              -- for non-token providers (PublicWWW, Exa, etc.) — just counts the call
  cost_estimate_usd NUMERIC(10,4),        -- computed at write time from a small pricing map in code; re-check
                                           -- periodically, same staleness caveat as model selection in §0.4
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE provider_budgets (
  provider TEXT PRIMARY KEY,
  monthly_quota INT,                      -- interpretation is provider-specific: query count for PublicWWW,
                                           -- USD-cents for LLM providers, etc. — document the unit per row you insert
  notes TEXT
);

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_campaigns_updated_at
BEFORE UPDATE ON campaigns
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_candidates_updated_at
BEFORE UPDATE ON candidates
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_leads_updated_at
BEFORE UPDATE ON leads
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Performance indexes (H1)
-- =============================================================================

-- Fast LATERAL join in /api/leads: evaluations per candidate
CREATE INDEX IF NOT EXISTS idx_evaluations_candidate_id ON evaluations(candidate_id);

-- Fast LATERAL join in /api/leads: feedback per candidate
CREATE INDEX IF NOT EXISTS idx_feedback_candidate_id ON feedback(candidate_id);

-- Fast status filter in Stage 5 enrichment loop and /api/leads
CREATE INDEX IF NOT EXISTS idx_candidates_status_campaign ON candidates(campaign_id, status);

-- Composite index covering WHERE campaign_id=X AND status='new' ORDER BY created_at ASC
CREATE INDEX IF NOT EXISTS idx_candidates_campaign_status_created ON candidates(campaign_id, status, created_at ASC) WHERE status = 'new';

-- Fast candidates creation date sorting
CREATE INDEX IF NOT EXISTS idx_candidates_created_at ON candidates(created_at DESC);

-- Fast lookup for evaluated candidates dashboard queries
CREATE INDEX IF NOT EXISTS idx_candidates_evaluated_at ON candidates(evaluated_at DESC) WHERE evaluated_at IS NOT NULL;

-- Partial index: Stage 5 only ever queries status='approved'
CREATE INDEX IF NOT EXISTS idx_candidates_approved ON candidates(status) WHERE status = 'approved';

-- Fast budget monitoring metrics aggregation
CREATE INDEX IF NOT EXISTS idx_api_call_log_campaign_created ON api_call_log(campaign_id, created_at);

-- =============================================================================
-- Campaign settings column (documented above in CREATE TABLE)
-- Added in migration 0008
CREATE INDEX IF NOT EXISTS candidates_claim_idx ON candidates (status, lease_expires_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS leads_candidate_id_uniq ON leads(candidate_id);
-- =============================================================================

-- The settings column stores dashboard slider values as JSONB:
-- { "min_score_for_review": 50, "max_enrichment_attempts": 3,
--   "enrichment_retry_hours": 24, "search_cooldown_days": 30,
--   "max_candidates_per_run": 200, "max_enrichment_per_run": 20,
--   "min_evidence_urls": 1 }
-- (Added in base schema; no ALTER TABLE needed post-deployment).

-- =============================================================================
-- Search queries log (used by Stage 2 cooldown)
-- =============================================================================

CREATE TABLE IF NOT EXISTS search_queries_log (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  query_yield_count INT DEFAULT 0,
  last_run_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(campaign_id, query)
);
