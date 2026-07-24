-- Phase X Schema Extensions
BEGIN;

-- MainWP tracking on leads
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS email_sent_at        TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS plugin_download_at   TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS plugin_installed_at  TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS mainwp_site_id       TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS converted_at         TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS mainwp_webhook_token TEXT UNIQUE DEFAULT NULL;

-- Audit token on candidates
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS audit_token         TEXT UNIQUE DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS audit_token_created TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS audit_viewed_at     TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS audit_view_count    INT DEFAULT 0;

-- Malware KB quality fields
ALTER TABLE malware_signatures
    ADD COLUMN IF NOT EXISTS sneakiness_tier    TEXT DEFAULT 'C',
    ADD COLUMN IF NOT EXISTS proof_method       TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outreach_hook      TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS outbreak_scope     TEXT DEFAULT 'global';

COMMIT;
