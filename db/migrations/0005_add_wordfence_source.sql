-- Migration: 0005_add_wordfence_source.sql
-- Adds Wordfence and Sucuri as threat intel sources

INSERT INTO threat_intel_sources (name, url, type, status)
VALUES 
  ('Wordfence Blog', 'https://www.wordfence.com/feed/', 'rss', 'active'),
  ('Sucuri Blog', 'https://blog.sucuri.net/feed', 'rss', 'active'),
  ('WPScan Vulnerability DB', 'https://wpscan.com/blog/feed/', 'rss', 'active')
ON CONFLICT DO NOTHING;
