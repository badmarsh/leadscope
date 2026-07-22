-- Stabilization migration — idempotent, safe to re-run
-- Run with: psql -U leadscope -d leadscope -f db/migrations/0001_stabilization.sql

BEGIN;

-- 1. Add source_article column to malware_signatures (used by threat intel ingestion)
ALTER TABLE malware_signatures ADD COLUMN IF NOT EXISTS source_article TEXT;

-- 2. Add standalone UNIQUE constraint on snippet for global signatures (where campaign_id IS NULL)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'malware_signatures_snippet_global_unique'
  ) THEN
    -- Index for NULL campaign_id global unique snippets
    CREATE UNIQUE INDEX idx_malware_signatures_global_snippet ON malware_signatures (snippet) WHERE campaign_id IS NULL;
  END IF;
EXCEPTION
  WHEN duplicate_table THEN NULL;
END $$;

-- 3. Fast domain lookups on candidates
CREATE INDEX IF NOT EXISTS idx_candidates_domain ON candidates(domain);

-- 4. Fast candidate lookup on leads
CREATE INDEX IF NOT EXISTS idx_leads_candidate_id ON leads(candidate_id);

-- 5. Fast candidate lookup on evaluations
CREATE INDEX IF NOT EXISTS idx_evaluations_candidate_id ON evaluations(candidate_id);

COMMIT;
