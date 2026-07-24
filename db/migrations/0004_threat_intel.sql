-- Migration: 0004_threat_intel.sql
-- Adds the threat_intel_sources table and the status column to malware_signatures

CREATE TABLE IF NOT EXISTS threat_intel_sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL, -- 'rss', 'sitemap', 'api'
    last_checked_at TIMESTAMPTZ DEFAULT NULL,
    status TEXT DEFAULT 'active', -- 'active', 'disabled'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add status to malware_signatures to support human-in-the-loop review
ALTER TABLE malware_signatures
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'; -- 'pending', 'approved', 'rejected'
