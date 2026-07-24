INSERT INTO intel_queries (campaign_id, name, engine, query_string, snipexp_regex)
SELECT id, 'SocGholish (NDSW URLScan free-text)', 'urlscan', 'ndsw', NULL
FROM campaigns WHERE slug = 'wp-remediation';

INSERT INTO intel_queries (campaign_id, name, engine, query_string, snipexp_regex)
SELECT id, 'SocGholish (khutmhpx URLScan free-text)', 'urlscan', 'khutmhpx', NULL
FROM campaigns WHERE slug = 'wp-remediation';

INSERT INTO intel_queries (campaign_id, name, engine, query_string, snipexp_regex)
SELECT id, 'WP2Shell (Exposed REST API batch endpoint)', 'urlscan', 'page.url:"/wp-json/batch/v1"', NULL
FROM campaigns WHERE slug = 'wp-remediation';

INSERT INTO intel_queries (campaign_id, name, engine, query_string, snipexp_regex)
SELECT id, 'SocGholish Loader (PublicWWW Snipexp)', 'publicwww_snipexp', '"insertBefore(a,b)" filetype:js', '|src=["''](https?://[a-z0-9.-]+)|'
FROM campaigns WHERE slug = 'wp-remediation';
