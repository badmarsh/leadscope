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

## The Three Pipeline Families

### Family 1: Lead Generation (main pipeline)
**Files:** `services/stages/stage1.py`, `stage2.py`, `stage5.py`, `services/evaluator/`
**Campaigns:** JENEX HVAC Hungary (DB id=1), Shoe Photo Upgrade (DB id=2), WP Remediation (DB id=3)
**Entry point:** `app/api/campaigns/[id]/pipeline/route.ts` -> n8n workflow triggers

**Audit tasks:**
- Verify the `llm.chat_json` return signature is consistent across all callers (stages vs evaluator use different tuple sizes - 3-tuple vs 5-tuple)
- Check `services/stages/stage2.py` search provider priority order: which of Exa / Tavily / Serper / SerpAPI / Brave is actually configured and hitting live results vs silently returning `[]`?
- Check `services/stages/stage5.py` enrichment: is the zero-data guard (`if not email and not phone and not report`) actually preventing empty lead records? Test with a real candidate
- Check `services/evaluator/scorers/content_relevance.py`: confirm it now uses `CRAWLER_ENDPOINT` (Crawl4AI) not Firecrawl for primary scraping (was just migrated)
- Verify `services/evaluator/scorers/image_quality.py` and `threat_intel.py` still work correctly with the evaluator's 5-tuple `llm.chat_json`
- Check `services/evaluator/harness.py`: what is `min_score_for_review`? Is the default `20` still appropriate after the Firecrawl->Crawl4AI migration? If scrape quality improved, scores will be higher - consider adjusting
- Run: `SELECT campaign_id, status, COUNT(*) FROM candidates GROUP BY campaign_id, status ORDER BY campaign_id, status;` to see current funnel health
- Run: `SELECT COUNT(*) FROM leads WHERE contact_email IS NULL AND created_at > now() - interval '7 days';` to measure zero-enrichment rate this week

---

### Family 2: WP Compromise Hunter (/wp-hunter)
**Files:** `wp-hunter/src/wp_hunter/`, `wp-hunter/campaigns.yaml`, `app/wp-hunter/page.tsx`, `app/api/wp-hunter/`

**What this tool does (for the owner):**
The WP Hunter is a passive OSINT pipeline that finds WordPress sites compromised by specific malware families (SocGholish, Balada Injector, etc.). It works in 3 stages:
- **Stage A (Ingest):** Takes a PublicWWW CSV export (or pulls from URLhaus/ThreatFox) containing domains that match a malware signature
- **Stage B (Pivot):** Looks those domains up in urlscan.io and VirusTotal to confirm infection and find related domains
- **Stage C (Report):** Merges all findings into a CSV + Markdown report of confirmed infected businesses - your leads for the WP Remediation campaign

**Audit tasks:**
- Read `wp-hunter/campaigns.yaml` fully. Identify which campaign entries are **templates** (contain `{{PLACEHOLDER}}` text) and which are live. Templates must **never** be run - verify the code in `cli.py` and `schema.py` enforces this with a hard error
- Verify that `freshness_gate()` in `wp-hunter/src/wp_hunter/schema.py` actually blocks stale campaigns (check `stale_after_days` logic)
- Check `wp-hunter/src/wp_hunter/ingest_abusech.py`: does the URLhaus feed pull actually work? Test with a live HTTP call to `https://urlhaus-api.abuse.ch/v1/urls/recent/` and verify the response is parsed correctly
- Check `wp-hunter/src/wp_hunter/pivot_urlscan.py`: does the urlscan.io search API require an API key? Check `config` or `.env.example` to confirm `URLSCAN_API_KEY` is documented
- Check `wp-hunter/src/wp_hunter/pivot_vt.py`: the `vt_graph` flag in `cli.py` enables VT graph-walk pivot. Is this flag exposed in the dashboard UI (`app/wp-hunter/page.tsx`)? Is it safe to run without rate limits?
- Check `app/api/wp-hunter/run/route.ts`: does the dashboard "Run" button actually shell out to the `wp-hunter` CLI? Verify the subprocess call, working directory, and env var injection
- **End-to-end test:** Using campaign `socgholish-ndsw`, run the full pipeline from the dashboard. Verify findings appear in the Findings table. If it fails, fix it
- **Key toggle to explain:** `--vt-pivot-domains` vs `--vt-graph` - what do each do, what do they cost (API quota), and what should the defaults be?

---

### Family 3: SEO Spam Hunter (/seo-spam-hunter)
**Files:** `seo-spam-hunter/src/seo_spam_hunter/`, `seo-spam-hunter/campaigns.yaml`, `app/seo-spam-hunter/page.tsx`, `app/api/seo-spam-hunter/`

**What this tool does (for the owner):**
The SEO Spam Hunter finds WordPress sites that have been injected with SEO spam (Japanese keyword hack, pharma link injection, hidden link farms). These are different from malware - instead of infecting visitors, the attacker injects thousands of fake pages to steal the site's Google ranking. These site owners are leads for remediation services.

**Audit tasks:**
- Read `seo-spam-hunter/campaigns.yaml` fully. Identify template entries (contain `{{ANCHOR_TEXT_KEYWORD}}`) and verify the pipeline refuses to run them
- Check `seo-spam-hunter/src/seo_spam_hunter/pivot_wayback.py`: the Wayback Machine pivot is unique to this tool. Verify it correctly calls the CDX API (`http://web.archive.org/cdx/search/cdx`) and parses historical snapshots. Is there a rate limit issue?
- Check `seo-spam-hunter/src/seo_spam_hunter/cluster.py`: what does the domHash clustering do? Is it actually producing useful groupings for the pharma-hack campaign?
- Check `seo-spam-hunter/src/seo_spam_hunter/ingest_abusech.py`: is this file identical to the wp-hunter version? If so, consolidate into a shared library to avoid drift
- Check `app/api/seo-spam-hunter/run/route.ts`: same subprocess pattern as wp-hunter - verify it works
- **End-to-end test:** Run the `pharma-hack-hidden-links` campaign from the dashboard. Verify findings appear. Fix any failures
- **Key toggle to explain:** `wayback_pivot.enabled` - when should this be true vs false, and how much slower does it make the run?

---

### Family 4: Threat Feeds (/threat-feeds)
**Files:** `app/threat-feeds/page.tsx`, `services/jobs/certstream_monitor.py`, `services/jobs/urlhaus_monitor.py`, `services/jobs/urlscan_monitor.py`

**Audit tasks:**
- Check `services/jobs/certstream_monitor.py`: is the certstream container (`jenex_ai-certstream-1`) healthy? Run `docker compose logs certstream --tail=50`. It is currently marked `(unhealthy)` - find out why and fix it
- Check what data the threat-feeds page actually displays. Is it reading from the database or a static source?
- Verify the certstream monitor's keyword filters are appropriate for the WP Remediation campaign

---

## Settings & Toggles Reference (Create This Document)

After the audit, create a file at `.agents/PIPELINE_SETTINGS_GUIDE.md` in the repo containing:

For **every** configurable toggle, threshold, or setting across all pipelines:
- **What it is** (plain English, no jargon)
- **Current value** (read from code/config, do not assume)
- **What happens if too high / too low**
- **Recommended value** based on current usage patterns and API quotas
- **Where to change it** (exact file and line number)

Include these known settings at minimum:
- `min_score_for_review` (harness.py)
- `stale_after_days` per campaign (campaigns.yaml files)
- `--vt-pivot-domains` and `--vt-graph` flags
- `wayback_pivot.enabled` per campaign
- `threatfox_days` (ingest_feeds command)
- `max_enrichment_per_run` (stage5 / campaign settings)
- `max_candidates_per_run` (stage2 / campaign settings)
- `search_cooldown_days` (stage2 query deduplication)
- `enrichment_retry_hours` (stage5 retry logic)

---

## Verification Checklist

Before finishing, confirm each item with a check or X and evidence:

- [ ] All Docker containers are healthy (`docker compose ps`)
- [ ] Stage 2 (Candidate Finder) produces results for WP Remediation - check DB for `new` candidates created in last 24h
- [ ] Stage 3 (Evaluator) is processing candidates - check DB for `evaluated` or `pending_review` status changes in last 24h
- [ ] Stage 5 (Enrichment) produces leads with non-null `contact_email` - query leads table
- [ ] WP Hunter `socgholish-ndsw` campaign runs end-to-end without errors
- [ ] SEO Spam Hunter `pharma-hack-hidden-links` campaign runs end-to-end without errors
- [ ] Certstream container is healthy and producing CT log events
- [ ] No template campaigns (`{{PLACEHOLDER}}`) can be accidentally run from any UI
- [ ] All API keys referenced in `.env.example` are present in the runtime environment

---

## Deliverables

1. **All bugs fixed** with commits and pushes
2. **`.agents/PIPELINE_SETTINGS_GUIDE.md`** committed to repo - the plain-language settings reference
3. **A summary** of what was broken, what was fixed, and what optimal settings were set
