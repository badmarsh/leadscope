-- Add domain_authority to candidates
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS domain_authority INT DEFAULT NULL;

-- Add mx_valid and linkedin_url to contacts
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS mx_valid BOOLEAN DEFAULT NULL;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS linkedin_url TEXT DEFAULT NULL;

-- Create composite performance index on candidates
CREATE INDEX IF NOT EXISTS idx_candidates_pipeline_perf ON candidates(campaign_id, status, created_at DESC);

-- Create filtered index on contacts
CREATE INDEX IF NOT EXISTS idx_contacts_mx_valid ON contacts(candidate_id, mx_valid) WHERE mx_valid = true;
