-- 0002_performance_and_features.sql
-- Performance indexes and schema additions for Phase 6 features

-- Candidates status lookup (used by every stage poll query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_campaign_status
    ON candidates (campaign_id, status);

-- Few-shot feedback lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_feedback_candidate_decision
    ON feedback (candidate_id, decision);

-- Cost dashboard queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_call_log_campaign_created
    ON api_call_log (campaign_id, created_at DESC);

-- Duplicate domain guard: one active evaluation per domain per campaign.
-- Partial index excludes 'duplicate' status rows so they don't block re-discovery.
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_domain_campaign_active
    ON candidates (domain, campaign_id)
    WHERE status NOT IN ('duplicate', 'discarded', 'stale');

-- DNC domain lookup (wildcard match uses LIKE, but a regular btree on domain covers equality branch)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dnc_domain
    ON do_not_contact (domain);

-- Email quality classification added by 6.6
ALTER TABLE leads ADD COLUMN IF NOT EXISTS email_quality TEXT
    CHECK (email_quality IN ('personal', 'role', 'invalid'))
    DEFAULT NULL;

-- ICP Drift Detection columns (Feature 6.10)
ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS icp_drift_suggestion JSONB DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS icp_drift_analyzed_at TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS icp_drift_decisions_at_analysis INTEGER DEFAULT 0;

-- Evaluations columns (Feature 6.1)
ALTER TABLE evaluations 
    ADD COLUMN IF NOT EXISTS score_confidence varchar(10) DEFAULT 'medium',
    ADD COLUMN IF NOT EXISTS reeval_triggered boolean DEFAULT false;

-- Leads column for drafted subject lines (Feature 6.4)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS draft_subject_lines text[] DEFAULT '{}';
