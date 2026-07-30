BEGIN;

ALTER TABLE candidates
  ADD COLUMN IF NOT EXISTS processing_generation bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS lease_id uuid,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;

CREATE INDEX IF NOT EXISTS candidates_claim_idx
  ON candidates (status, lease_expires_at, id);

CREATE UNIQUE INDEX IF NOT EXISTS leads_candidate_id_uniq ON leads(candidate_id);

COMMIT;
