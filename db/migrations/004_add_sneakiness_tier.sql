ALTER TABLE malware_signatures
  ADD COLUMN IF NOT EXISTS sneakiness_tier VARCHAR(1) DEFAULT 'C',
  ADD COLUMN IF NOT EXISTS proof_method TEXT;
CREATE INDEX IF NOT EXISTS idx_sigs_sneakiness ON malware_signatures(sneakiness_tier);
