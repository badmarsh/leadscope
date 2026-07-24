# Pipeline Operations Audit & Optimization Prompt

> **Preamble:** The `leadscope` repository is attached to this conversation via a GitHub connector.
> Read and open every file you reference. Do not assume file content or folder structure.
> Treat the live running Docker environment as the ground truth — run `docker compose ps` and
> `docker compose logs` to verify actual runtime state before drawing conclusions.

---

## Your Mission

You are a senior site-reliability and sales-ops engineer conducting a full audit of the
**Jenex AI leadscope platform**. The owner understands the business goals but does not
understand the technical configuration of the pipelines, what the toggles do, whether
settings are optimal, or whether all the tools are actually working end-to-end.

Your job is to:
1. **Read every relevant file** (do not assume)
2. **Verify each pipeline actually runs** end-to-end
3. **Fix anything that is broken or misconfigured**
4. **Document what each toggle/setting does in plain language**
5. **Set optimal defaults** and justify each choice
6. Produce a final **plain-language ops guide** the owner can actually use

---

## Campaign A: JENEX HVAC Hungary (DB id=1)

**What this campaign does:** Finds Hungarian HVAC distributors, installers, and
manufacturers who are potential distribution partners for JENEX products. It searches
the web for companies in the HVAC/ventilation space in Hungary, evaluates each
candidate against an ICP (Ideal Customer Profile), enriches confirmed leads with
contact data, and presents them for manual review.

**Pipeline scorer:** `content_relevance` — evaluates whether the site is actually
an HVAC company in the right geography and size range.

**Audit tasks:**
- Read `services/evaluator/scorers/content_relevance.py`. Confirm the scraper is now
  using `CRAWLER_ENDPOINT` (Crawl4AI) rather than Firecrawl. This was just migrated —
  verify the implementation is correct and the bot-challenge detection (`_is_bot_challenge`)
  is working properly since many Hungarian B2B sites use Cloudflare.
- Read `services/stages/stage2.py`. The JENEX campaign uses Hungarian keyword queries.
  Check the `keywords_hu` in the ICP config: run
  `SELECT icp_config FROM campaigns WHERE id = 1;` and verify the keywords are correct
  and up to date. Are there any queries in `search_queries_log` that yielded 0 results?
  Run: `SELECT query, query_yield_count, last_run_at FROM search_queries_log WHERE campaign_id = 1 ORDER BY last_run_at DESC LIMIT 20;`
- Check `services/stages/stage2.py` — the `publicwww_scraper.py` integration. Is
  PublicWWW being used for this campaign? What query is being used? Is the `depth:all`
  flag set? Verify the scraper is not running into HTTP 429 rate limits.
- DB funnel check: `SELECT status, COUNT(*) FROM candidates WHERE campaign_id = 1 GROUP BY status;`
  and `SELECT COUNT(*) FROM leads WHERE campaign_id = 1 AND contact_email IS NOT NULL;`
- The campaign is currently `status = 'draft'` in the database. Determine whether it
  should be activated to `active` or intentionally kept on pause. If it should run,
  activate it: `UPDATE campaigns SET status = 'active' WHERE id = 1;`
- Check if the 55 enriched leads in the `leads` table are actually visible in the
  dashboard and displaying correctly (domain, score, rationale, contact info).

**Key settings to document:**
- `search_cooldown_days` for campaign 1 — how many days before the same query is re-run?
- `max_candidates_per_run` — how many new domains does Stage 2 process per execution?
- `min_score_for_review` — what score threshold gates a candidate into the review queue?

---

## Campaign B: Shoe Photo Upgrade (DB id=2)

**What this campaign does:** Finds e-commerce shoe boutiques that sell footwear but
have poor product photography. The opportunity score is inverted — a HIGH score means
the business is a GOOD lead (active, sells shoes, but has bad photos). The pitch is
a professional product photography upgrade service.

**Pipeline scorer:** `image_quality` — uses a vision LLM to look at actual product
photos pulled from the site and score them on photography quality, relevance to shoes,
and business activity signals.

**Audit tasks:**
- Read `services/evaluator/scorers/image_quality.py` in full. This scorer still uses
  `firecrawl_client.scrape_domain_pages()` for its primary scraping — it was NOT
  migrated to Crawl4AI unlike `content_relevance.py`. Determine if this is intentional
  (Firecrawl's HTML mode gives better `<img>` tag extraction for product grids) or
  whether it suffers the same SPA rendering problem. Check whether
  `firecrawl_client.extract_product_grid_images()` is being called with `include_html=True`
  and whether this produces real product image URLs or mostly empty results on
  Shopify/WooCommerce stores.
- Check `firecrawl_client.py`'s `_discover_product_paths()` — does the dynamic path
  discovery actually find `/products`, `/termekek`, `/shop` etc. for Hungarian stores?
  Or is it defaulting to the static fallback list on every call?
- DB funnel check: `SELECT status, COUNT(*) FROM candidates WHERE campaign_id = 2 GROUP BY status;`
  The campaign has 141 `new` candidates and 1 `discarded` — why has nothing been
  evaluated? Is the evaluator simply not running for campaign 2, or is the ICP config
  missing/malformed? Run: `SELECT icp_config FROM campaigns WHERE id = 2;`
- The campaign is currently `status = 'draft'`. If it has 141 waiting candidates and
  a working ICP, it should be activated. Verify the ICP exists first.
- Check whether `firecrawl_client` has a valid `FIRECRAWL_API_KEY` and
  `FIRECRAWL_ENDPOINT` in the runtime environment:
  `docker compose exec evaluator env | grep FIRECRAWL`
- **Consider migrating `image_quality.py` to Crawl4AI** if Firecrawl is returning
  poor results. The key difference: image_quality needs real `<img>` src URLs from
  the product grid, not just markdown text. Test both approaches on a sample Shopify
  store URL before deciding.

**Key settings to document:**
- The inverted scoring logic: explain why a score of 80 means "great lead" (bad photos)
  not "bad lead" (irrelevant site)
- `evaluator_type` field — what determines which scorer runs for which campaign?
  Read `services/evaluator/harness.py` to find where this routing happens

---

## Campaign C: WP Malware Remediation (DB id=3)

**What this campaign does:** Finds WordPress websites actively infected with malware
(SocGholish, Balada Injector, Sign1, etc.) and reaches out to the business owner
offering remediation services. The pipeline uses PublicWWW to match known malware
signatures in page source, then re-verifies with a live Crawl4AI scrape, and
optionally checks Google Safe Browsing and VirusTotal before scoring.

**Pipeline scorer:** `threat_intel` — re-verifies infection, checks external security
databases, scores by infection severity and business value.

**Audit tasks:**
- Read `services/evaluator/scorers/threat_intel.py` in full. This is the most complex
  scorer. Verify:
  - The `WP_PATHS` list (`""`, `/wp-content/`, `/wp-includes/`) — are these the right
    paths to scan? Should `/wp-admin/` or `/xmlrpc.php` be checked?
  - `calculate_wealth_index()` — the TLD-based wealth score. Is `.sk`, `.cz`, `.pl`
    classified correctly? These are target markets.
  - The `snippet_confirmed` check — does it correctly detect if the malware signature
    is still present in a fresh Crawl4AI scrape?
  - Optional integrations: `SAFE_BROWSING_API_KEY` and `VIRUSTOTAL_API_KEY` — are
    these set in the environment? Run: `docker compose exec evaluator env | grep -E 'SAFE_BROWSING|VIRUSTOTAL'`
  - `scorers/proof_engine.py` and `scorers/exposure_scanner.py` — what do these do?
    Are they being called? Do they have any rate limits or failure modes?
- Read `services/stages/stage2.py` for the WP campaign specifically. The signatures
  used in PublicWWW queries come from the IOC signatures table. Run:
  `SELECT id, family, snippet, publicwww_query FROM ioc_signatures WHERE active = true LIMIT 20;`
  Are these signatures current? Check the `stale_after_days` logic — are any signatures
  past their freshness date and silently returning empty results?
- Check `db/migrations/0006_seed_ioc_signatures.sql` — what signatures were seeded?
  Are they all in the database? Run:
  `SELECT COUNT(*) FROM ioc_signatures;`
- DB funnel check: campaign 3 has 53,926 `new` candidates and 510 `pending_review`.
  This is a very large queue. Is the evaluator processing them fast enough? What is the
  current evaluator throughput? Check `docker compose logs evaluator --tail=100` for
  processing rate.
- The `stale_after_days` concept from wp-hunter campaigns — does the main lead gen
  pipeline have an equivalent mechanism? Check if any IOC signatures have expired.

**Key settings to document:**
- `SAFE_BROWSING_API_KEY` — what does this enable, how much does it cost, is it worth it?
- `VIRUSTOTAL_API_KEY` — same questions
- `wealth_index` formula — is the TLD-based scoring accurate for target markets?
- `snippet_confirmed` threshold — what counts as "confirmed" vs "inconclusive"?

---

## Pipeline D: WP Compromise Hunter (/wp-hunter)

**What this tool does:** A passive OSINT pipeline that finds WordPress sites
compromised by specific malware families using PublicWWW signature matching, urlscan.io
pivoting, and VirusTotal cross-referencing. Output is a report of confirmed infected
businesses — direct leads for the WP Remediation campaign.

**Files:** `wp-hunter/src/wp_hunter/`, `wp-hunter/campaigns.yaml`,
`app/wp-hunter/page.tsx`, `app/api/wp-hunter/`

**Active campaigns:**
- `socgholish-ndsw` — SocGholish via `ndsw` JS variable (stable, long-term signature)
- `socgholish-khutmhpx` — SocGholish via `khutmhpx` (HTML body injection)
- `balada-fake-plugin-template` — **TEMPLATE**, requires manual slug substitution before running
- `wp2shell-cve-2026-63030` — server-side RCE, routes to pivot-only (no PublicWWW)

**Audit tasks:**
- Verify `freshness_gate()` in `wp-hunter/src/wp_hunter/schema.py` correctly blocks:
  (a) campaigns past `stale_after_days` without `--i-know-this-is-stale` flag
  (b) template entries containing `{{PLACEHOLDER}}` text
- Check `app/api/wp-hunter/run/route.ts` — how does the dashboard Run button actually
  execute the CLI? Find the subprocess call and verify the working directory and env
  vars are correct. Run it manually: try the `socgholish-ndsw` campaign from the
  dashboard and watch the execution terminal for errors.
- Check `wp-hunter/src/wp_hunter/ingest_abusech.py` — does the URLhaus live feed
  actually return data? Run a quick test:
  `curl -s https://urlhaus-api.abuse.ch/v1/urls/recent/ | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('urls',[])), 'recent URLs')"`
- Check `pivot_urlscan.py` — does it require `URLSCAN_API_KEY`? What happens without it?
- Check `pivot_vt.py` — the `--vt-graph` flag enables graph-walk pivot. Is this exposed
  in the dashboard UI? What is the API cost per graph-walk? Is it rate-limited correctly?
- Document exactly what `--vt-pivot-domains` does vs `--vt-graph`:
  - `--vt-pivot-domains`: looks up each found domain in VT, gets its contacted_domains
    list — adds 1 VT API call per domain found
  - `--vt-graph`: walks the VT relationship graph from seed domains — can cascade into
    100s of API calls. Should be OFF by default, ON only for deep investigations.

**Key settings to document:**
- `stale_after_days` per campaign (current values and whether they are appropriate)
- `max_pages` in the pivot command (default 10 — how many urlscan result pages)
- Whether `--vt-pivot-domains` should be the default for routine runs
- Whether `--vt-graph` should ever be ON by default (almost certainly NO)

---

## Pipeline E: SEO Spam Hunter (/seo-spam-hunter)

**What this tool does:** Finds WordPress sites injected with SEO spam — fake pages
designed to steal Google rankings rather than infect visitors. Types include Japanese
keyword hack (gibberish slugs with Japanese pharmacy keywords), pharma hack (hidden
buy-viagra links in CSS), and link farms. Site owners are leads for remediation.

**Files:** `seo-spam-hunter/src/seo_spam_hunter/`, `seo-spam-hunter/campaigns.yaml`,
`app/seo-spam-hunter/page.tsx`, `app/api/seo-spam-hunter/`

**Active campaigns:**
- `japanese-keyword-hack` — detects JP-language gibberish slug injection
- `pharma-hack-hidden-links` — detects hidden buy-viagra/cialis link injection
- `wp-vcd-backdoor` — WP-VCD functions.php injection (pivot-only, no PublicWWW)
- `spam-link-network-template` — **TEMPLATE**, requires anchor text substitution

**Audit tasks:**
- Confirm template enforcement — run the `spam-link-network-template` campaign from the
  dashboard and verify it errors out rather than running with the `{{PLACEHOLDER}}` query
- Check `pivot_wayback.py` — this tool is unique to SEO Spam Hunter. Verify:
  - It correctly calls `http://web.archive.org/cdx/search/cdx`
  - The `match_mime: text/html` filter is working
  - It handles Wayback rate limiting (they throttle aggressively — is there a backoff?)
- Check `cluster.py` — the domHash clustering groups sites that share the same injected
  HTML scaffold. Verify the clustering algorithm produces coherent groups. Is it
  producing any output for `pharma-hack-hidden-links`?
- Check `ingest_abusech.py` in seo-spam-hunter vs wp-hunter — are these two files
  identical copies? If so, consolidate into a shared utility to prevent drift.
- Run `pharma-hack-hidden-links` end-to-end from the dashboard. Verify findings appear.
- Check `app/api/seo-spam-hunter/run/route.ts` — verify subprocess execution pattern
  identical issues as wp-hunter.

**Key settings to document:**
- `wayback_pivot.enabled` — true vs false: Wayback pivots take 30-60s per domain.
  When is it worth enabling vs slowing down a full run?
- `cluster.py` domHash minimum cluster size — below what size does a cluster get discarded?
- `stale_after_days` for pharma-hack (30) vs japanese-keyword-hack (45) — rationale?

---

## Pipeline F: Threat Intel Feeds (/threat-feeds)

**What this tool does:** A real-time monitoring dashboard that aggregates three live
threat intelligence streams:
1. **Certificate Transparency (CT) logs** via CertStream — watches for new SSL
   certificates issued to suspicious domains that match WordPress compromise patterns
2. **URLhaus feed** — pulls URLs from abuse.ch that are actively distributing malware
3. **urlscan.io monitor** — watches urlscan's live submission stream for WordPress sites
   flagged as malicious

Findings from these feeds are candidates for the WP Remediation pipeline.

**Files:**
- `services/jobs/certstream_monitor.py` — CT log subscriber
- `services/jobs/urlhaus_monitor.py` — URLhaus feed puller
- `services/jobs/urlscan_monitor.py` — urlscan live monitor
- `services/jobs/discovery_helpers.py` — shared DB helpers
- `app/threat-feeds/page.tsx` — dashboard UI
- `components/pipeline-dashboard/CtTickerWidget.tsx` — live CT log ticker

**Audit tasks:**

**CRITICAL — Certstream container is `(unhealthy)`:**
Run `docker compose logs certstream --tail=100` and find the exact error. Common causes:
- `services/jobs/certstream_monitor.py` crashing on startup (import error, missing dep)
- The `docker compose` health check is misconfigured
- The `0rickyy0/certstream-server-go` image is failing to connect to the CT log stream
Check `docker compose.yml` for the `certstream` service definition — what is the health
check command? What port does it listen on? Is the internal `certstream-server` container
healthy independently of the `certstream` job container?

- Read `services/jobs/certstream_monitor.py` in full:
  - `HIGH_VALUE_TLDS` set — is `.sk`, `.cz`, `.pl`, `.hu` included for target markets?
    Currently it includes `.de`, `.fr` etc. but not `.sk` or `.hu`. Add if missing.
  - `EXCLUDED_DOMAINS` set — is it too aggressive? Could it be filtering out legitimate targets?
  - `passes_heuristics()` — the domain length filter (`len(name) < 4 or > 35`) — is
    this appropriate? Many real businesses have short names.
  - `--check-wp` flag — does verifying `/wp-login.php` existence work? Test manually.
  - `--max-inserts` flag — what is the default? Is it appropriate for overnight runs?

- Check `services/jobs/urlhaus_monitor.py`:
  - How often does it poll? Is there a scheduled trigger or does it run once?
  - Does it correctly filter to only WordPress-related URLs?
  - Does it insert into `candidates` table with correct `campaign_id = 3`?

- Check `services/jobs/urlscan_monitor.py`:
  - Does it use the urlscan.io live feed WebSocket or the search API?
  - What queries does it use? Are they producing results?

- Check `app/threat-feeds/page.tsx` and `CtTickerWidget.tsx`:
  - Where does the live CT log ticker get its data? Is it reading from the DB or
    connecting directly to the certstream WebSocket?
  - Is the "Ingest All Feeds" button on the Threat Feeds page actually wired up to
    run all wp-hunter and seo-spam-hunter feed ingestions? Verify the API calls.

- Check `db/migrations/0004_threat_intel.sql` and `0003_phase_x.sql` — have these
  migrations been applied to the running database? Run:
  `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;`

**Key settings to document:**
- `HIGH_VALUE_TLDS` in certstream — which TLDs are monitored and why
- `--check-wp` flag — what it does, cost (1 HTTP request per domain), default recommendation
- `--max-inserts` limit — why it exists, what happens without it
- URLhaus polling frequency — how current is the data?

---

## Settings & Toggles Reference (Create This Document)

After the audit, create a file at `.agents/PIPELINE_SETTINGS_GUIDE.md` in the repo.

For **every** configurable toggle, threshold, or setting across all pipelines:
- **What it is** (plain English, no jargon)
- **Current value** (read from code/config, do not assume)
- **What happens if too high / too low**
- **Recommended value** with justification
- **Where to change it** (exact file and variable/line)

Minimum required settings to cover:

| Setting | File | Notes |
|---|---|---|
| `min_score_for_review` | `harness.py` | Gate between Stage 3 and review queue |
| `max_candidates_per_run` | campaign settings JSONB | Stage 2 throughput limiter |
| `max_enrichment_per_run` | campaign settings JSONB | Stage 5 throughput limiter |
| `search_cooldown_days` | campaign settings JSONB | Prevents re-running same query too soon |
| `enrichment_retry_hours` | campaign settings JSONB | When a failed enrichment gets retried |
| `stale_after_days` | each campaigns.yaml | WP Hunter / SEO Hunter freshness gate |
| `--vt-pivot-domains` | wp-hunter CLI | Adds 1 VT API call per found domain |
| `--vt-graph` | wp-hunter CLI | Graph walk — can cost 100s of API calls |
| `wayback_pivot.enabled` | seo-spam-hunter campaigns.yaml | Adds 30-60s per domain |
| `threatfox_days` | seo/wp-hunter CLI | How far back ThreatFox looks |
| `max_pages` | wp/seo-hunter pivot | urlscan.io result page limit |
| `HIGH_VALUE_TLDS` | certstream_monitor.py | Which countries' sites are monitored |
| `--check-wp` | certstream_monitor.py | Whether to verify WordPress before inserting |
| `--max-inserts` | certstream_monitor.py | Safety cap on overnight runs |
| `SAFE_BROWSING_API_KEY` | evaluator env | Enables Google Safe Browsing checks |
| `VIRUSTOTAL_API_KEY` | evaluator env | Enables VT re-verification in threat_intel scorer |

---

## Verification Checklist

Before finishing, confirm each item with evidence (DB query output or log excerpt):

**Lead Generation**
- [ ] Campaign 1 (JENEX): `leads` table has enriched records with `contact_email IS NOT NULL`
- [ ] Campaign 2 (Shoes): ICP config exists and evaluator can process its 141 waiting candidates
- [ ] Campaign 3 (WP Remediation): evaluator is processing the 510 `pending_review` candidates
- [ ] No `llm.chat_json` tuple unpack mismatches anywhere (all callers use correct 3 or 5 tuple)

**WP Hunter**
- [ ] `socgholish-ndsw` runs end-to-end from dashboard without errors
- [ ] Template campaigns (`balada-fake-plugin-template`) cannot be run — verified with hard error
- [ ] URLhaus live feed returns data
- [ ] `--vt-graph` is OFF by default in the dashboard UI

**SEO Spam Hunter**
- [ ] `pharma-hack-hidden-links` runs end-to-end from dashboard without errors
- [ ] Template campaign (`spam-link-network-template`) cannot be run
- [ ] Wayback pivot produces output for japanese-keyword-hack campaign
- [ ] `ingest_abusech.py` is not duplicated (or duplication is documented as intentional)

**Threat Feeds**
- [ ] Certstream container is `(healthy)` after fixes
- [ ] `.sk` and `.hu` TLDs are in `HIGH_VALUE_TLDS` (Slovak and Hungarian target markets)
- [ ] URLhaus monitor inserts candidates into DB with `campaign_id = 3`
- [ ] All DB migrations (0003-0006) have been applied
- [ ] Threat Feeds page displays live data, not static placeholders

---

## Deliverables

1. **All bugs fixed** — commits and pushes for every fix
2. **`.agents/PIPELINE_SETTINGS_GUIDE.md`** — committed to repo
3. **Summary** — what was broken, what was fixed, what optimal settings were applied
