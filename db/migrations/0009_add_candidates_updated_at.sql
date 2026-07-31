-- Migration 0009: Add missing updated_at column to candidates
-- The schema.sql already defines this column and a trigger for it,
-- but the live DB was created before this column was added.

ALTER TABLE candidates
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- Back-fill: set updated_at = created_at for existing rows so it's not NULL
UPDATE candidates SET updated_at = created_at WHERE updated_at IS NULL;

-- Create the trigger helper function if missing (defined in schema.sql but absent in live DB)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';

-- Wire up the trigger
DROP TRIGGER IF EXISTS set_candidates_updated_at ON candidates;

CREATE TRIGGER set_candidates_updated_at
  BEFORE UPDATE ON candidates
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
