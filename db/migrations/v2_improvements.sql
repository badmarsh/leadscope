-- Pipeline V2 Improvements Migrations
ALTER TABLE leads ADD COLUMN IF NOT EXISTS firmographics JSONB;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS buying_power_signals TEXT[];
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tech_stack TEXT[];
ALTER TABLE leads ADD COLUMN IF NOT EXISTS cold_email_hook TEXT;
