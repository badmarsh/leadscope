-- Migration: 0006_seed_ioc_signatures.sql
-- Seeds known high-value Indicators of Compromise (IoCs) and GitHub repos as sources

-- 1. Add GitHub repositories to sources
INSERT INTO threat_intel_sources (name, url, type, status)
VALUES 
  ('stefanpejcic/wordpress-malware', 'https://api.github.com/repos/stefanpejcic/wordpress-malware/git/trees/master?recursive=1', 'github', 'active'),
  ('ecrider/Black-SEO-WordPress-Malware', 'https://api.github.com/repos/ecrider/Black-SEO-WordPress-Malware/git/trees/main?recursive=1', 'github', 'active')
ON CONFLICT DO NOTHING;

-- 2. Seed known high-value IoCs
-- We insert these as 'active' because they are researcher-validated
INSERT INTO malware_signatures (campaign_id, snippet, malware_family, source_url, confidence, sneakiness_tier, proof_method, outreach_hook, outbreak_scope, status)
VALUES
  (3, 'eval(base64_decode(', 'Generic PHP Backdoor', 'https://github.com/stefanpejcic/wordpress-malware', 'high', 'A', 'Scan for base64 eval in PHP files', 'Your site contains an obfuscated PHP backdoor.', 'global', 'active'),
  (3, 'add_action(''init'',''wpb_admin_account'')', 'Hidden Admin Backdoor', 'https://github.com/cyber-insect99/Backdoor-and-Web-shell', 'high', 'A', 'Check WordPress users list for unauthorized admins', 'Attackers have created a hidden administrator account on your site.', 'global', 'active'),
  (3, 'wp_create_user', 'Hidden Admin Backdoor', 'https://github.com/cyber-insect99/Backdoor-and-Web-shell', 'high', 'A', 'Check WordPress users list for unauthorized admins', 'Attackers have created a hidden administrator account on your site.', 'global', 'active'),
  (3, 'eval(String.fromCharCode', 'JS Obfuscation / Keylogger', 'https://heimdalsecurity.com/blog/wordpress-websites-files-and-databases-injected-with-malicious-javascript/', 'high', 'B', 'Scan database and JS files for obfuscated code', 'Your site is infected with an obfuscated JavaScript keylogger.', 'global', 'active'),
  (3, 'md5($_GET[''backdoor''])', 'URL-Triggered Backdoor', 'https://github.com/cyber-insect99/Backdoor-and-Web-shell', 'high', 'A', 'Check theme functions.php for malicious URL triggers', 'Your site contains a hidden backdoor triggered by a specific URL.', 'global', 'active'),
  (3, 'preg_replace.*\/e', 'PHP Code Execution', 'https://blog.securelayer7.net/backdoor-php-code-wordpress/', 'high', 'A', 'Scan PHP files for deprecated preg_replace /e modifier', 'Your site uses deprecated PHP functions to execute malicious code.', 'global', 'active'),
  (3, 'cdjs[.]online', 'Keylogger C2', 'https://www.thetilt.com/content/protect-wordpress-site-keylogger-malware', 'high', 'S', 'Check network requests for cdjs.online', 'Your site is communicating with a known keylogger command and control server.', 'global', 'active'),
  (3, 'cdns[.]ws', 'Keylogger C2', 'https://www.thetilt.com/content/protect-wordpress-site-keylogger-malware', 'high', 'S', 'Check network requests for cdns.ws', 'Your site is communicating with a known keylogger command and control server.', 'global', 'active'),
  (3, 'ois[.]is', 'Black-Hat SEO Redirect', 'https://securityaffairs.com/138523/hacking/wordpress-sites-black-hat-seo.html', 'high', 'B', 'Check Google Search Console for manual actions or unexpected redirects', 'Your site is being used to redirect visitors to spam sites.', 'global', 'active'),
  (3, 'spadeanalytica[.]com', 'Malicious Analytics JS', 'https://blog.sucuri.net/2024/12/malicious-script-injection-on-wordpress-sites.html', 'high', 'B', 'Check header.php for unauthorized script injections', 'Your site is loading a malicious script disguised as analytics.', 'global', 'active'),
  (3, '/* trackmyposs*/', 'JS Keylogger Marker', 'https://heimdalsecurity.com/blog/wordpress-websites-files-and-databases-injected-with-malicious-javascript/', 'high', 'S', 'Scan JS files for trackmyposs marker', 'Your site is infected with a known JavaScript keylogger.', 'global', 'active'),
  (3, 'add_action(''wp_head'', ''WordPress_backdoor'')', 'URL-Triggered Backdoor', 'https://github.com/cyber-insect99/Backdoor-and-Web-shell', 'high', 'A', 'Check theme functions.php for malicious URL triggers', 'Your site contains a hidden backdoor triggered by a specific URL.', 'global', 'active'),
  (3, 'function wp_vcd', 'WP-VCD Malware Family', 'https://blog.sucuri.net/2020/01/backdoor-found-in-compromised-wordpress-environment.html', 'high', 'S', 'Scan theme functions.php for wp_vcd', 'Your site is infected with the WP-VCD malware family.', 'global', 'active')
ON CONFLICT (campaign_id, snippet) DO UPDATE SET 
  status = 'active',
  sneakiness_tier = EXCLUDED.sneakiness_tier,
  proof_method = EXCLUDED.proof_method,
  outreach_hook = EXCLUDED.outreach_hook,
  confidence = EXCLUDED.confidence;
