# Multi-vertical lead-generation platform — coding agent build megaprompt

**Companion to:** `leadgen-platform-v0-gui-prompt.md` — a separate, standalone prompt for v0 (Vercel's UI generator). This document is for a coding agent (Claude Code or similar).

**Revision 3** — content carried over from the single-file v3 revision, split here by which tool consumes it, plus the directory-input framing below (marked `>> ADDED (split):`).

## Inputs already in this working directory

This document assumes you're working in a project directory that already contains:

- **`.env`** — populated with some or all of the keys listed in §0.5. Read what's there; don't overwrite existing values; if a key this build actually needs is blank, stop and flag it rather than inventing a placeholder or proceeding silently.
  - **Special case — `DATABASE_URL`:** if this key is blank or still the literal placeholder `postgresql://...`, that is **not** a blocker to flag and stop on. It means no external Postgres exists yet. Part 1 handles this: it creates the database via Docker Compose and then writes the correct `DATABASE_URL` back into `.env`. Do not stop here; proceed to Part 1.
- **The v0 GUI export** — the project exported from running `leadgen-platform-v0-gui-prompt.md` in v0.app, as a zip file or an already-extracted folder somewhere in this directory (check both a `.zip` and an already-unzipped folder before assuming it's missing). **Only Part 4b depends on this.** Parts 0–3 and 5–8 have no dependency on the dashboard's existence at all and should proceed regardless of whether the export has landed yet — don't block the rest of the build waiting on it.

Everything else below is unchanged in substance from the v3 build spec.

---

This is structured as a sequence of **self-contained parts**. Each part embeds the minimal schema excerpt it depends on, so it can be worked on individually without needing the rest of this document loaded as context. Part 0 + Part 1's full DDL should still be kept in context alongside every part where possible; the embedded excerpts are a fallback, not a replacement.

Each part ends with a **validation & testing** checklist; don't start the next part until the current one's checklist passes. Part 0 isn't a build task — it's shared reference material every other part draws from.

---

## Part 0 — Shared context (read only)

### 0.1 The one hard rule, every part, every campaign
No agent in this system ever contacts anyone. Every output is a draft row in a database table, reviewed and sent by a human.

### 0.2 Campaign abstraction
A **campaign** bundles: a business brief, reference materials, a finder strategy (`keyword_search` or `code_signature_search`), an evaluator strategy (`content_relevance`, `image_quality`, or `threat_intel`), and an enrichment/outreach tone. Everything else — n8n workflows, the evaluator service, the dashboard, spend tracking, and the do-not-contact list — is shared infrastructure parameterized by `campaign_id`.

>> NOTE (judgment call): the evaluator registry stays hardcoded per `evaluator_type` (three Python strategies behind a shared harness), not a generic prompt-config engine. With three known campaigns and one permanent operator, a config-driven evaluator would be building flexibility nobody's asked for. If a fourth vertical shows up later, Part 3's registry is the extension point — add a fourth strategy function, not a new system.

### 0.3 Business context per campaign

**Campaign 1 — JENEX HVAC (Hungary)**
- Company: JENEX Dobšiná, s.r.o. — Kúpeľná 983, Dobšiná 049 25, Slovakia. Founded 1997. Director: Ing. Tibor Jedinák. `obchod@jenexsro.sk` (sales), `info@jenexsro.sk` (general).
- Product in scope — SWAH corner brackets (patented, galvanized-steel corner connectors for SWAH-type ventilation duct profiles):
  - `20SH` — standard — order no. 400 100 020 — 300 pcs/box
  - `20LSH` — extended — order no. 400 100 021 — 300 pcs/box
  - `30SH` — larger profile — order no. 400 100 030 — 300 pcs/box
- Reference catalogs (ground Stage 1 in these, don't invent product details beyond them):
  - `https://www.jenexsro.sk/en/product-catalog/`
  - `https://www.jenexsro.sk/wp-content/uploads/2022/11/Jenex-2022-en.pdf`
  - `https://www.jenexsro.sk/wp-content/uploads/2024/10/JENEX-PROFESSIONAL-QUALITY-VENTILATION-2024.pdf`
- JENEX already publishes `jenexsro.sk/hu/` — usable directly in Stage 5 drafts, and a signal of existing HU-market intent.
- Target types: HVAC wholesalers/distributors, ductwork fabricators, HVAC construction/projektant firms, in Hungary.

**Campaign 2 — Shoe-photo-upgrade**
- Offer: AI-generated upgraded product images and short product videos, built from a store's existing catalogue.
- Target: e-commerce shoe boutiques whose product photography is flat, single-angle, plain-background "photo booth" style rather than styled lifestyle photography.
- *Fill in before running Stage 1:* your service's name, pricing/positioning, and any existing portfolio/before-after examples to ground the brief.

**This campaign's `campaigns.status` must be inserted as `'draft'`, not `'active'`, until the brief above is filled in.** Stage 1 (Part 2) must not run against a placeholder brief — see the `status='draft'` gate in Part 1 and Part 2.

**Campaign 3 — WP-remediation**
- Offer: paid malware-cleanup consultation, offered once a site is verified compromised.
- Target: WordPress sites carrying known-malicious injected code, detected via signature match (§Part 5) and re-verified before outreach (§Part 3, evaluator C).
- *Fill in before running Stage 1:* your service's name, pricing/positioning, and geographic/niche focus if any.

**Same `status='draft'` gate as shoe-photo-upgrade — with one exception: Part 5 (signature ingestion) does NOT depend on this brief and may run immediately regardless of draft status.** Only Stage 1 (ICP/brief definer) and everything downstream of it (Stages 2–5, Part 3's evaluator, Part 4 review) are blocked by the placeholder.

A do-not-contact list and a cooldown on re-discovering previously-rejected/stale domains (Part 1 §`do_not_contact`/`candidates.reopen_count`, Part 7) enforce "don't keep re-pitching the same site" at the system level.

### 0.4 LLM assignment

| Stage | Default model | Note |
|---|---|---|
| 1. Brief/ICP definer | Gemini 3 Flash (local proxy) | cheap, low-volume |
| 2. Target finder | Gemini 3 Flash (local proxy) | structuring/dedup |
| 3. Deep evaluator | OpenRouter → strong frontier model | accuracy here determines lead quality everywhere |
| 5. Enrichment | Local Ollama (RTX 3090) | templated extraction + short drafting, zero marginal cost |
| Signature extraction (Part 5 ingestion) | Gemini 3 Flash (local proxy) | cheap structured extraction from blog text |

Shoe-photo-upgrade's evaluator needs a **vision-capable** call (Gemini 3 Flash and most current OpenRouter frontier models both take image input — no new infra needed, just pass images through in the harness for that campaign type).

**Re-check Gemini's flash-tier lineup before locking these model strings in.** Gemini 3 Flash (this table's default) is real and current, but Google's Flash line has kept moving underneath it — a 3.1 Flash-Lite tier optimized specifically for cheap high-volume structuring exists, and a 3.5 Flash generation has since reached general availability. Stages 1, 2, and signature extraction are exactly the "cheap structuring" workloads a lite tier is priced for — verify pricing/quality yourself rather than building around the table above unchecked.

**Gemini SDK — use `google-genai`, not `google-generativeai`:** the older `google-generativeai` package is end-of-life (EOL) and no longer receives updates. All Gemini calls in this project (Stages 1, 2, signature ingestion) must use the current `google-genai` package:

```bash
pip install google-genai
```

The proxy-compatible client construction pattern (confirmed working against `GEMINI_PROXY_ENDPOINT`):

```python
from google import genai
from google.genai import types

client = genai.Client(
    api_key=os.environ["GEMINI_PROXY_API_KEY"],
    http_options={"base_url": os.environ["GEMINI_PROXY_ENDPOINT"]},
)

response = client.models.generate_content(
    model="gemini-3-flash",          # or whichever flash-tier variant you've verified
    contents="Your prompt here",
    config=types.GenerateContentConfig(temperature=0.2),
)
result_text = response.text
```

For structured/JSON output (Stages 1 and 2 produce JSON), add `response_mime_type="application/json"` to `GenerateContentConfig`. For vision calls (shoe-photo evaluator), pass image bytes via `types.Part.from_bytes(data=..., mime_type="image/jpeg")` alongside the text prompt in a `contents` list.

**OpenRouter calls (Stage 3 evaluator):** use the OpenAI-compatible SDK pointed at OpenRouter's endpoint:

```bash
pip install openai
```

```python
import openai

openrouter = openai.OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

# Use a strong frontier model — verify current best option on openrouter.ai/models
response = openrouter.chat.completions.create(
    model="anthropic/claude-sonnet-4",  # or your preferred model; check pricing
    messages=[{"role": "user", "content": "..."}],
    temperature=0.2,
)
result_text = response.choices[0].message.content
```

For the vision-capable shoe-photo evaluator, pass images as base64-encoded `image_url` content parts in the messages array — both Claude and Gemini models on OpenRouter support this.

### 0.5 Secrets checklist

>> REVISED (split): a `.env` file already exists in this directory — **read it, don't recreate it.** Confirm which of the keys below are populated. If any key a part you're building actually needs is blank, stop and surface that rather than fabricating a value or skipping the check silently. Never print secret values back into chat/logs; never paste them anywhere outside the credential manager or this file. Rotate anything that was ever pasted into a chat window.

Confirm your self-hosted Firecrawl instance's version supports the specific features this spec relies on — JS-rendered page scraping (Part 2/3) and PDF extraction (Part 3, JENEX catalog PDFs). Self-hosted Firecrawl can lag the cloud product's API surface by several releases; test both feature paths against your actual endpoint before assuming parity with Firecrawl's public docs.

Confirm PublicWWW's account tier and per-query rate limit before wiring Stage 2's `code_signature_search` or Part 6.1's nightly re-verification job — the query-budget gate in §0.6/Part 2 needs the real number from your account tier to be useful; it can only refuse to over-spend against a quota you've actually entered into `provider_budgets`.

Expected keys (some or all may already be filled in `.env`):

```
EXA_API_KEY=
TAVILY_API_KEY=
SERPER_API_KEY=
SERPAPI_API_KEY=
BRAVE_SEARCH_API_KEY=
PUBLICWWW_API_KEY=
OPENROUTER_API_KEY=
GEMINI_PROXY_ENDPOINT=http://127.0.0.1:8045
GEMINI_PROXY_API_KEY=
OLLAMA_HOST=http://localhost:11434
FIRECRAWL_ENDPOINT=https://firecrawl.dev.significa.sk
FIRECRAWL_API_KEY=
DATABASE_URL=postgresql://...
DASHBOARD_PASSWORD_HASH=            # bcrypt hash, not the raw password — see Part 4b
DASHBOARD_SESSION_SECRET=           # random string, signs the session cookie — see Part 4b
```

### 0.6 Cost & quota tracking baseline

One table, `api_call_log` (Part 1), records every paid API/LLM call made anywhere in the system — which campaign, which stage, which provider, tokens or query count, an estimated cost. It does double duty:

- **Cost visibility** — query it per-campaign to see which vertical is actually eating your API spend.
- **Quota budgeting** — `provider_budgets` (Part 1) holds a monthly cap per provider (e.g. PublicWWW's query allowance). Before Stage 2's `code_signature_search` or Part 6.1's re-verification job fires a batch of PublicWWW queries, it sums this month's usage from `api_call_log` and skips the batch if it's at or over budget — deferring to the next scheduled run rather than erroring or silently burning through your quota. This is a "check before you spend" gate, not a real job queue — deferring to the next poll cycle is the queue.

This is deliberately lightweight: no dashboard-grade analytics, no alerting service — just a log table, a budget table, and a check before spend. Part 6.4 adds the one periodic job that reads them.

---

## Part 1 — Database schema & infra foundation

**Goal:** provision a local Postgres instance via Docker Compose, apply the full schema, seed initial campaign rows, and produce a working `docker-compose.yml` skeleton for the rest of the platform services (n8n, evaluator, dashboard).

**If `DATABASE_URL` in `.env` is blank or is the literal placeholder `postgresql://...`:** that means there is no pre-existing database. Follow the provisioning steps below before running any DDL.

**Step 1 — Provision Postgres via Docker Compose (skip if DATABASE_URL is already a real, reachable connection string):**

Create (or draft into) `docker-compose.yml` a `postgres` service first — before the other services — so it can be started independently:

```yaml
# docker-compose.yml  (stub — other services added below)
services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: leadscope
      POSTGRES_PASSWORD: leadscope_dev   # change before any non-local use
      POSTGRES_DB: leadscope
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Then:
1. Run `docker compose up -d postgres` to start only the Postgres service.
2. Wait for it to be healthy: `docker compose exec postgres pg_isready -U leadscope`
3. Update `.env` — replace the placeholder value with the real connection string:
   ```
   DATABASE_URL=postgresql://leadscope:leadscope_dev@localhost:5432/leadscope
   ```
   Do this by editing the file in-place; do not wipe other keys.
4. Confirm connectivity from the host: `psql "$DATABASE_URL" -c "SELECT 1"`
   If `psql` is not available locally, use: `docker compose exec postgres psql -U leadscope -d leadscope -c "SELECT 1"`

**Step 2 — Apply schema (DDL deliverable):**

```sql
CREATE TABLE campaigns (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,             -- 'jenex-hu-hvac', 'shoe-photo-upgrade', 'wp-remediation'
  name TEXT NOT NULL,
  finder_type TEXT NOT NULL,             -- 'keyword_search' | 'code_signature_search'
  evaluator_type TEXT NOT NULL,          -- 'content_relevance' | 'image_quality' | 'threat_intel'
  business_brief TEXT,                   -- nullable; use status='draft' to gate placeholder briefs
  reference_materials JSONB,
  status TEXT DEFAULT 'active',          -- active | paused | draft
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT brief_required_unless_draft
    CHECK (status = 'draft' OR business_brief IS NOT NULL)
);

CREATE TABLE icp_config (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id),
  version INT NOT NULL,
  target_segments JSONB NOT NULL,
  keywords_hu TEXT[],
  keywords_en TEXT[],
  disqualifiers JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE malware_signatures (       -- WP-remediation's knowledge base (Part 5 feeds it,
  id SERIAL PRIMARY KEY,                -- Part 2's finder consumes it)
  campaign_id INT REFERENCES campaigns(id),
  snippet TEXT NOT NULL,
  malware_family TEXT,
  source_url TEXT CHECK (source_url IS NULL OR source_url LIKE 'http%'),
  confidence TEXT DEFAULT 'medium',      -- low | medium | high
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(campaign_id, snippet)
);

CREATE TABLE candidates (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id),
  company_name TEXT,
  domain TEXT NOT NULL,
  source TEXT,
  query_used TEXT,
  evidence_data JSONB,                    -- discovery-time evidence (e.g. which signature(s) matched)
  status TEXT DEFAULT 'new',              -- new | evaluated | pending_review | approved | rejected | enriched | stale | enrichment_failed
  enrichment_attempted_at TIMESTAMPTZ,     -- tracks Stage 5 attempts so Firecrawl failures don't loop silently
  enrichment_attempt_count INT DEFAULT 0,  -- caps retries (Part 2, Stage 5) — see MAX_ENRICHMENT_ATTEMPTS
  last_seen_at TIMESTAMPTZ DEFAULT now(),  -- bumped whenever Stage 2 re-encounters this domain
  reopen_count INT DEFAULT 0,              -- how many times a stale candidate got reopened by rediscovery
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(campaign_id, domain)
);

CREATE TABLE do_not_contact (
  id SERIAL PRIMARY KEY,
  domain TEXT NOT NULL,
  campaign_id INT REFERENCES campaigns(id),  -- NULL = suppress this domain across every campaign
  reason TEXT,
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(domain, campaign_id)
);

CREATE TABLE evaluations (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id),
  score INT,                              -- 0-100, always "how good an opportunity this is"
  rationale TEXT,
  evidence_urls TEXT[],
  evidence_data JSONB,                    -- vertical-specific structured evidence
  model_used TEXT,
  icp_version_used INT,                   -- records which icp_config.version this score was computed against
  status TEXT DEFAULT 'pending_review',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feedback (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id),
  decision TEXT NOT NULL,                 -- approved | rejected
  note TEXT,
  reviewed_by TEXT,                       -- single permanent operator: leave free-text/nullable, no user model needed
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads (
  id SERIAL PRIMARY KEY,
  candidate_id INT REFERENCES candidates(id) UNIQUE,
  campaign_id INT REFERENCES campaigns(id),  -- denormalized for direct per-campaign dashboard queries without a join through candidates
  contact_email TEXT,
  contact_name TEXT,
  draft_email TEXT,
  enriched_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_call_log (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id),   -- nullable: some calls (e.g. signature ingestion) aren't cleanly one campaign's spend
  stage TEXT NOT NULL,                    -- 'stage1' | 'stage2' | 'stage3' | 'stage5' | 'signature_ingestion' | 'reverification'
  provider TEXT NOT NULL,                 -- 'gemini' | 'openrouter' | 'ollama' | 'exa' | 'tavily' | 'serper' | 'serpapi' | 'brave' | 'publicwww' | 'firecrawl'
  model TEXT,                             -- NULL for non-LLM providers
  tokens_in INT,
  tokens_out INT,
  query_count INT DEFAULT 1,              -- for non-token providers (PublicWWW, Exa, etc.) — just counts the call
  cost_estimate_usd NUMERIC(10,4),        -- computed at write time from a small pricing map in code; re-check
                                           -- periodically, same staleness caveat as model selection in §0.4
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE provider_budgets (
  provider TEXT PRIMARY KEY,
  monthly_quota INT,                      -- interpretation is provider-specific: query count for PublicWWW,
                                           -- USD-cents for LLM providers, etc. — document the unit per row you insert
  notes TEXT
);
```

**Extend** the `docker-compose.yml` created in Step 1 (do not create a separate compose file) with additional service stubs for `n8n`, `evaluator` (placeholder FastAPI container, built out in Part 3), and `dashboard` (placeholder, built out in Part 4). >> REVISED (split): the `dashboard` service's build context will be the v0 export already present in the project root (see Part 4) — don't scaffold a fresh Next.js app; the placeholder just needs a working Dockerfile pointing at the existing Next.js files.

**Validation & testing:**
- [ ] `docker compose up -d postgres` starts cleanly; `pg_isready` returns `accepting connections`
- [ ] `DATABASE_URL` in `.env` is updated to the real connection string (not the placeholder `postgresql://...`)
- [ ] `psql "$DATABASE_URL" -c "SELECT 1"` succeeds (or equivalent via `docker compose exec`)
- [ ] All tables created; foreign keys resolve
- [ ] Insert one `campaigns` row per vertical (`jenex-hu-hvac` as `active` with a real brief; `shoe-photo-upgrade` and `wp-remediation` as `status='draft'` with `business_brief = NULL`) — confirm the `brief_required_unless_draft` check constraint allows this and rejects an `active` row with a NULL brief. For JENEX's `business_brief`, compose it from §0.3: include the company identity (JENEX Dobšiná, Slovakia), the specific SWAH corner bracket products (20SH, 20LSH, 30SH), target types (HVAC wholesalers/distributors, ductwork fabricators, HVAC construction/projektant firms), and geographic focus (Hungary). Keep it factual and grounded in the reference catalogs.
- [ ] Insert a `candidates` row with a bad `campaign_id` and confirm it's rejected (FK constraint works)
- [ ] Insert the same `domain` under two different `campaign_id`s and confirm it succeeds; insert the same `domain` twice under the *same* `campaign_id` and confirm it's rejected (`UNIQUE(campaign_id, domain)` behaves as intended)
- [ ] Insert a `candidates` row with `status='stale'` and confirm it's accepted (Part 6.1 depends on this value existing)
- [ ] Insert a `candidates` row with `status='enrichment_failed'` and confirm it's accepted
- [ ] Insert a `do_not_contact` row (one with a `campaign_id`, one with it NULL) and confirm both accept
- [ ] Insert a `provider_budgets` row for `publicwww` with a real monthly quota number, and an `api_call_log` row referencing it; confirm both accept
- [ ] `docker compose up` brings up all four services without errors

---

## Part 2 — n8n workflows: stages 1, 2, 5

**Goal:** generic, `campaign_id`-parameterized workflows — not one copy per campaign.

**Minimal schema excerpt this part depends on** (see Part 1 for full DDL): `campaigns(status, business_brief, finder_type)`, `icp_config`, `candidates(evidence_data, status, enrichment_attempt_count, last_seen_at, reopen_count)`, `malware_signatures`, `do_not_contact`, `leads`, `api_call_log`, `provider_budgets`.

**Stage 1 must check `campaigns.status` before running.** If `status = 'draft'`, refuse to run and surface a clear error ("business brief not yet filled in for this campaign — see §0.3") rather than generating an ICP from a placeholder brief.

**Stage 1 (Brief/ICP definer):** takes a campaign's `business_brief` + `reference_materials`, produces a structured ICP as JSON (target segments, HU/EN keywords, disqualifiers), inserts a new versioned `icp_config` row. Model: Gemini 3 Flash via local proxy — use the `google-genai` SDK pattern in §0.4, with `response_mime_type="application/json"` to get structured output directly. Write a row to `api_call_log` (`stage='stage1'`) for the call.

**Stage 2 (Target finder) — router on `campaigns.finder_type`:**
- `keyword_search` (JENEX, shoe-photo-upgrade): waterfall — Exa first, Tavily if a query returns under ~5 hits, Serper/SerpAPI for direct/`site:*.hu`-style queries, Brave for coverage. Run HU and EN variants. LLM (Gemini 3 Flash via local proxy — see §0.4 SDK pattern) structures/dedupes results into `candidates`.
- `code_signature_search` (WP-remediation): for each active `malware_signatures` row (for this campaign), query PublicWWW's source-code search for that snippet. Each hit → a `candidates` row with `evidence_data` populated with which signature(s) matched.

**Search API client guidance:** use each provider's official Python SDK where available (`exa-py` for Exa, `tavily-python` for Tavily, `google-search-results` for SerpAPI). For Brave Search, use raw HTTP requests with `BRAVE_SEARCH_API_KEY` as a Bearer token against `https://api.search.brave.com/res/v1/web/search`. For PublicWWW, use raw HTTP requests against their API endpoint with `PUBLICWWW_API_KEY` — consult their current API docs for response format, as it's less standardized than the others.

**Before any candidate insert, check `do_not_contact`** (matching either `(domain, campaign_id)` or `(domain, NULL)`). If present, skip the domain entirely — don't insert.

**Domain re-discovery must upsert, not blind-insert.** Relying on `UNIQUE(campaign_id, domain)` alone means a repeat discovery *errors* the workflow run rather than being silently handled. Use:
```sql
INSERT INTO candidates (campaign_id, company_name, domain, source, query_used, evidence_data, last_seen_at)
VALUES ($1, $2, $3, $4, $5, $6, now())
ON CONFLICT (campaign_id, domain) DO UPDATE SET
  last_seen_at = now(),
  reopen_count = candidates.reopen_count + 1,
  evidence_data = EXCLUDED.evidence_data
WHERE candidates.status = 'stale'
  AND candidates.last_seen_at < now() - interval '90 days';
```
The `WHERE` clause on the `DO UPDATE` is the actual mechanism worth understanding: if the existing row's status is anything *other* than `stale` (i.e. `new`, `evaluated`, `approved`, `enrichment_failed`, or — deliberately — `rejected`), or it's `stale` but was last seen inside the 90-day cooldown, the condition fails and Postgres leaves the row untouched. No error, no duplicate, no silent re-open.

>> NOTE (v3, judgment call): `rejected` candidates are *never* auto-reopened by rediscovery, cooldown or not — a human already ruled that one out, and only Part 6.2's ICP-version re-scoring (which only touches `new`/`pending_review`, never `rejected`) is allowed to reconsider criteria, not rediscovery. The 90-day figure is a starting point, not a researched constant — adjust to taste.

**`code_signature_search` must check spend before firing.** Before querying PublicWWW, sum `query_count` from `api_call_log` where `provider='publicwww'` and `created_at` is in the current calendar month; compare against `provider_budgets.monthly_quota` for `publicwww`. If at or over budget, skip the remaining signature queries for this run — they'll be picked up on the next scheduled run rather than erroring or blowing through the account's rate limit. Log every PublicWWW query that *does* fire to `api_call_log`.

**Stage 5 (Enrichment):** implement as an n8n workflow that polls `candidates.status='approved'`. Firecrawl scrapes the contact/impressum/`kapcsolat` page; local Ollama (called via HTTP API at `OLLAMA_HOST`) extracts a published email/name and drafts a 2–3 sentence opener using the campaign's offer framing. Inserts into `leads` (including `campaign_id`, denormalized). **After successfully inserting a `leads` row, update `candidates.status` to `'enriched'`** so the candidate moves out of the `approved` poll set and Part 6.1's re-verification job can find it. Never sends anything.

**Check `do_not_contact` before drafting anything.** If the candidate's domain is suppressed, leave it `approved` untouched (don't enrich, don't draft) — this is the honoring mechanism for "please stop contacting us" (Part 7).

On starting an enrichment attempt, set `candidates.enrichment_attempted_at = now()` and increment `enrichment_attempt_count` before calling Firecrawl. If the Firecrawl call fails and `enrichment_attempt_count < 3` (`MAX_ENRICHMENT_ATTEMPTS`), leave the candidate `approved` — the next poll cycle will retry, but only once `enrichment_attempted_at` is more than 24h old, so a fast-polling workflow doesn't hammer Firecrawl on the same failing target every cycle. If the call fails with `enrichment_attempt_count` already at 3, flip status to `enrichment_failed` instead of leaving it `approved` forever.

**Validation & testing:**
- [ ] Stage 1 run manually for JENEX produces a sane `icp_config` row (spot-check the keywords/segments against the brief)
- [ ] Attempt Stage 1 against a `draft`-status campaign (shoe-photo-upgrade or WP-remediation with placeholder brief) and confirm it refuses to run rather than producing a garbage `icp_config`
- [ ] Stage 2 `keyword_search`: run for JENEX with a trimmed keyword set, confirm 5–10 plausible candidates land with no duplicate domains within the campaign
- [ ] Confirm the same domain CAN appear as a candidate under two different campaigns (cross-campaign, not just within-campaign, dedup check)
- [ ] Stage 2 `code_signature_search`: seed 1–2 test rows in `malware_signatures` (a dummy/known snippet), run the finder, confirm the PublicWWW query executes and hits land as candidates tagged with the right signature in `evidence_data`
- [ ] Stage 5: manually flip one test candidate per non-draft campaign to `approved`, run enrichment, confirm a `leads` row appears with a draft that references the right campaign's offer (not a mismatched one), and confirm `enrichment_attempted_at` and `enrichment_attempt_count` are set
- [ ] Simulate a Firecrawl failure during Stage 5 (bad URL/timeout) and confirm the candidate stays `approved` with the attempt counted, rather than silently erroring with no trace
- [ ] Simulate 3 consecutive Firecrawl failures for the same candidate; confirm it flips to `enrichment_failed` on the 3rd rather than polling forever
- [ ] Insert a `do_not_contact` row for a test domain, confirm Stage 2 skips inserting a fresh candidate for it, and confirm Stage 5 does not draft for it even if a pre-existing `approved` candidate shares that domain
- [ ] Seed a `stale` candidate with `last_seen_at` 100 days ago, run Stage 2 rediscovery against the same domain, confirm it reopens (`reopen_count` increments, status changes); repeat with `last_seen_at` 10 days ago and confirm it does NOT reopen
- [ ] Seed `provider_budgets` for `publicwww` with a tiny quota (e.g. 1) and pre-fill `api_call_log` to already be at that quota; run Stage 2's `code_signature_search` and confirm it skips querying rather than firing anyway

---

## Part 3 — Deep evaluator service (stage 3)

**Goal:** one shared harness, three pluggable scorer strategies behind a registry keyed by `campaigns.evaluator_type`.

**Minimal schema excerpt this part depends on:** `candidates`, `campaigns`, `icp_config`, `feedback`, `evaluations(icp_version_used)`, `api_call_log`.

**Harness (shared):** look up the candidate → look up its campaign config → retrieve the current `icp_config` version for that `campaign_id` (record it in `evaluations.icp_version_used`) → retrieve the *k* most similar past `feedback` decisions **for that same `campaign_id`** (few-shot pools must never cross campaigns) → dispatch to the matching scorer → write to `evaluations`. Write a row to `api_call_log` (`stage='stage3'`, `provider='openrouter'`, tokens + model) for every scoring call.

**A. `content_relevance` (JENEX)** — Firecrawl scrapes homepage/product/catalogue pages + linked PDFs; LLM scores relevance against the current `icp_config`. Verify your self-hosted Firecrawl build actually extracts text from linked PDFs (§0.5) before relying on this for JENEX's catalog PDFs specifically.

**B. `image_quality` (shoe-photo-upgrade)** — Firecrawl scrapes product pages, extracts image URLs, a vision-capable LLM call scores against a rubric (resolution, framing, lighting consistency, background clutter), specifically flagging flat/photo-booth-style shots. Score is an **opportunity score**, not a raw quality score: combine (poor photo quality) with (signs the business is active — product count, recent activity, working checkout) into one number where 100 always means "great lead," so the direction stays consistent with the other two campaigns.

**C. `threat_intel` (WP-remediation)** — detection already happened in Stage 2 (a PublicWWW hit against a known signature). This scorer's job is **re-verification, not detection**: PublicWWW's index can lag the live web, so do a fresh Firecrawl fetch of the homepage (and the specific page, if known) and confirm the snippet is *still present* before scoring highly. Reputation APIs (Safe Browsing/VirusTotal/urlscan.io) are optional secondary corroboration, not the primary check. The LLM turns the (re-verified) match into a rationale — which malware family, which signature, confirmed present as of when — it doesn't make the compromise call itself. Require this fresh re-verification before a candidate reaches `approved`; a mistaken "you're hacked" is costlier here than a mediocre lead anywhere else.

>> NOTE (v3, judgment call): the registry stays three hardcoded strategy functions behind the shared harness, not a database-driven prompt/config system. That would only pay off with more evaluator types than this system has, or other people authoring them — neither applies to a single permanent operator running three known campaigns. The registry itself (a dict/match keyed by `evaluator_type`) is the extension point if a fourth ever shows up.

**Validation & testing:**
- [ ] One unit test per scorer using a fixture candidate (mocked Firecrawl/PublicWWW response); confirm score lands in 0–100 and `evidence_data` matches the expected shape for that type
- [ ] For scorer B specifically, run two fixtures — one with deliberately poor/flat photos and one with professional photos, both otherwise-comparable "active business" signals — and confirm the poor-photo fixture scores *higher* (the opportunity-score direction is correct, not just "a number came out")
- [ ] Cross-campaign isolation test: seed `feedback` for two different campaigns, confirm scoring a candidate in campaign A never retrieves campaign B's feedback rows
- [ ] Golden-set regression check: 2–3 known-good and known-bad fixture candidates per vertical; confirm scores land in the expected high/low bands. Keep this fixture set — Part 6 reuses it
- [ ] Run the same fixture candidate through the evaluator twice with no changes; confirm scores don't swing wildly (if they do, the scorer needs a lower temperature or majority-vote before it's trustworthy in production)
- [ ] Confirm `evaluations.icp_version_used` is populated correctly and matches the `icp_config.version` active at scoring time
- [ ] Confirm each scoring call produces a corresponding `api_call_log` row with plausible token counts and a non-null `cost_estimate_usd`

**Stage 3 trigger:** add an n8n workflow (or a cron-driven script) that polls for candidates with `status='new'`, calls the evaluator service's scoring endpoint for each, and on success flips `candidates.status` to `pending_review`. This is the bridge between Stage 2 (which produces `new` candidates) and the dashboard (which displays `pending_review` candidates). Without it, the evaluator service has endpoints but nothing invokes them.

---

## Part 4 — Review dashboard

>> REVISED (split): the GUI prototype for this part is generated **separately**, by pasting the companion file `leadgen-platform-v0-gui-prompt.md` into v0.app — that step doesn't happen in this directory and isn't part of your job as the coding agent. What follows assumes that prototype's exported code already exists in the project root (the Next.js files are at the top level).

**Goal:** wire the v0-generated prototype to real data, running against this project's Postgres/FastAPI stack.

**Minimal schema excerpt this part depends on:** `candidates`, `evaluations`, `feedback`, `leads(campaign_id)`, `api_call_log`, `provider_budgets`.

**First step:** The v0 export lives directly in the project root — the Next.js files (`app/`, `components/`, `lib/`, `package.json`, etc.) are already at the top level alongside this megaprompt. Do NOT look for a zip or subfolder. Treat the existing project root as both the dashboard source and the overall project directory. The mock data file at `lib/leads-data.ts` has a `// MOCK DATA` comment at the top marking where to hook in real API calls.

**Deliverable:** replace the mock data with real reads/writes. Add Next.js API route handlers in `app/api/` that call Postgres directly (via a lightweight ORM like Prisma or raw `pg` queries). The Part 3 FastAPI evaluator remains a separate service for LLM scoring only — it does not serve dashboard data. Approve/Reject actions write a `feedback` row and flip `candidates.status`.

Persist the dark-mode toggle (localStorage or a cookie) rather than leaving it as unpersisted React state — minor, but it resets on every reload otherwise. (The v0 export already persists to localStorage under the key `leadscope-dark-mode` — verify this is intact, don't re-implement.)

**Before wiring authentication, generate the two missing credential values:**
1. Choose a dashboard password and generate its bcrypt hash:
   ```bash
   python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD_HERE', bcrypt.gensalt()).decode())"
   ```
   Write the hash (not the raw password) to `DASHBOARD_PASSWORD_HASH` in `.env`.
2. Generate a random session secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Write the result to `DASHBOARD_SESSION_SECRET` in `.env`.

**Add real authentication — a single shared password is enough, no user table needed.** Compare the submitted password against `DASHBOARD_PASSWORD_HASH` (bcrypt), and on success set a signed, httpOnly session cookie using `DASHBOARD_SESSION_SECRET`. Gate every dashboard route (Next.js middleware) and every API route handler behind this. This is intentionally the simplest thing that works for one permanent operator — not a login system built for multiple users, since there aren't any.

**Wire the header's usage readout to real numbers** — query `api_call_log` grouped by `provider`/`campaign_id` for month-to-date spend/query counts, and `provider_budgets` for the caps, and surface both.

**Wire the enrichment-failed filter** to `candidates.status='enrichment_failed'` so those leads are visibly separated from the normal pending-review queue rather than invisible until someone thinks to query for them.

**Validation & testing:**
- [ ] Dashboard loads real `pending_review` evaluations per campaign, not mock data
- [ ] Campaign switcher actually changes the displayed data set
- [ ] Approve/Reject writes to `feedback` and updates `candidates.status` correctly
- [ ] Evidence panel renders correctly per campaign type (images load for shoe-photo; malware family/source link show for WP; rationale/evidence URLs show for JENEX)
- [ ] dark-mode preference survives a page reload
- [ ] Loading the dashboard without a valid session cookie redirects to login; a wrong password is rejected; a correct password grants access and the session persists across a reload
- [ ] The usage readout reflects real `api_call_log`/`provider_budgets` data — seed a known set of log rows and confirm the displayed numbers match
- [ ] A candidate with `status='enrichment_failed'` shows up under the failed filter, not the default pending-review view

---

## Part 5 — Signature ingestion pipeline (WP-remediation only)

**Goal:** keep `malware_signatures` current.

**This part runs independently of the WP-remediation business brief (§0.3) and does not need to wait for `campaigns.status` to leave `draft`.** It only needs the `wp-remediation` campaign row to exist with a valid `id` — the brief itself is not read by this pipeline.

**Minimal schema excerpt this part depends on:**
```sql
CREATE TABLE malware_signatures (
  id SERIAL PRIMARY KEY,
  campaign_id INT REFERENCES campaigns(id),
  snippet TEXT NOT NULL,
  malware_family TEXT,
  source_url TEXT CHECK (source_url IS NULL OR source_url LIKE 'http%'),
  confidence TEXT DEFAULT 'medium',
  added_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(campaign_id, snippet)
);
```

**Deliverable:** a periodic job that scrapes named WP-security blogs (Wordfence, MalCare, Sucuri, etc. — your own curated list), uses an LLM (Gemini 3 Flash via local proxy — see §0.4 SDK pattern) to extract the code snippet, the malware family name if the post gives one, and a confidence level, then dedups and upserts into `malware_signatures`. Log each extraction call to `api_call_log` (`stage='signature_ingestion'`). Scrape blog posts using Firecrawl (same client as Parts 2/3, already configured at `FIRECRAWL_ENDPOINT`) or plain HTTP + BeautifulSoup if the blogs don't require JS rendering — most WP security blogs serve static HTML.

**Validation & testing:**
- [ ] Run once manually against a single chosen blog post; confirm the extracted snippet, `malware_family`, and `source_url` land correctly
- [ ] Run it a second time against the same post; confirm the dedup logic prevents a duplicate row for the same snippet
- [ ] Confirm the extracted `snippet` value is plausibly code (non-empty, no pure-prose sentences, reasonable length) — add a basic pattern/format check in the extraction step to catch LLM false positives (e.g. quoting a snippet mentioned in prose rather than the actual injected code)
- [ ] Confirm the extraction calls are landing in `api_call_log`

---

## Part 6 — Re-evaluation & maintenance jobs

These didn't exist in the original single-pass design — worth adding once the core pipeline runs, since leads and criteria both go stale.

**Minimal schema excerpt this part depends on:** `candidates(status, last_seen_at, reopen_count)`, `icp_config(version)`, `evaluations(icp_version_used)`, `feedback`, `api_call_log`, `provider_budgets`.

**6.1 Re-verification job (WP-remediation)** — a periodic job (nightly is reasonable) that re-checks `approved` or `enriched`-but-not-yet-contacted WP-remediation candidates against the live site. If the matched signature is no longer present, flip status to `stale` rather than deleting the row — the human reviewer should see it was once a real hit, not silently lose it. A site can get cleaned up between approval and a human actually sending outreach. This job also consumes PublicWWW/Firecrawl quota — check `provider_budgets` the same way Stage 2 does before firing (§Part 2) — and grows more expensive as `malware_signatures` grows, so schedule with that in mind.

This is a different mechanism from Stage 2's rediscovery-with-cooldown (Part 2): 6.1 re-checks a candidate the system already knows about and has already scored — it's a sanity check before a human sends outreach on something that might have changed. Stage 2's cooldown logic governs a *different* case: the same domain getting freshly discovered again later, independent of whether 6.1 ever touched it. A candidate 6.1 flips to `stale` is exactly the kind of row Stage 2's rediscovery logic is designed to potentially reopen later, once past the cooldown.

**6.2 Re-scoring on ICP version bump** — when Stage 1 produces a new `icp_config` version for a campaign, re-run Stage 3 only on candidates still in `new`/`pending_review` (i.e., not yet in `feedback`). Leave already-`approved`/`rejected` candidates alone — a human already ruled on those under the old criteria, and re-litigating past decisions isn't the goal. Confirm the re-scored `evaluations` rows carry the new `icp_version_used` value, not the stale one.

**6.3 Golden-set regression suite** — keep the fixture candidates from Part 3's validation step as a small permanent set per campaign. Re-run them through the evaluator any time a prompt or model changes, before trusting that scorer on real candidates again.

**6.4 Budget monitoring job** — a lightweight periodic job (daily is enough) comparing `api_call_log` usage against `provider_budgets.monthly_quota` for every tracked provider. If any provider crosses 80%/100% of its monthly quota, log a warning — a console/log line is sufficient for a single operator checking in regularly; wire it to email/Slack only if you find you're not checking logs often enough to notice.

**Validation & testing:**
- [ ] Simulate a WP-remediation candidate whose live site no longer contains the matched snippet; confirm the re-verification job flips it to `stale`, not silently dropped or left as `approved`
- [ ] Bump a test campaign's `icp_config` version; confirm only `new`/`pending_review` candidates get re-scored, decided ones are untouched
- [ ] Confirm the re-scored candidates' new `evaluations` rows show `icp_version_used` equal to the bumped version, not the prior one
- [ ] Run the golden-set suite twice with no changes; confirm stable scores. Run it again after any real prompt/model change before shipping that change
- [ ] Seed `api_call_log` to sit just under a test provider's `provider_budgets` quota; run 6.4 and confirm it logs a warning; seed it comfortably under and confirm it doesn't

---

## Part 7 — Compliance notes (not legal advice)

- JENEX and shoe-photo-upgrade: only publicly-published business contact info is surfaced; a human sends everything.
- WP-remediation: extra care applies (§Part 3, evaluator C) — multi-source-grade confirmation via fresh re-verification before approval, and Stage 5 drafts must cite the specific, checkable finding rather than vague or alarming language. The human-review gate matters more here than in the other two campaigns, not less. Worth your own judgment on how this offer is marketed given the "your site was compromised" framing.
- The do-not-contact list (Part 1, Part 2) and the rediscovery cooldown (Part 2) are the concrete mechanisms behind "don't keep re-approaching the same site." If someone ever replies asking not to be contacted again, that's a `do_not_contact` insert, not just a note to remember — it's honored automatically by every stage from then on, across every campaign if you leave `campaign_id` NULL. Similarly, a domain a human already rejected stays rejected permanently; only Stage 2 rediscovery of a `stale` (not `rejected`) domain, past a cooldown window, can ever bring a domain back into the pipeline.

## Part 8 — Open items

- ~~Decide whether new campaigns get added via a direct SQL insert into `campaigns`, or need a small "add campaign" form in the dashboard~~ — **resolved:** direct SQL insert. A form solves a problem (non-technical people adding campaigns) this build doesn't have.
- ~~Decide on a real reviewer/user identity model for `feedback.reviewed_by`~~ — **resolved:** not needed. Leave it free-text/nullable as Part 1 has it; there's exactly one reviewer, indefinitely.
- Re-check current Gemini flash-tier pricing/quality (3 Flash vs. 3.1 Flash-Lite vs. 3.5 Flash — §0.4) before finalizing the model assignment table.
- Set the real `provider_budgets.monthly_quota` values once you've confirmed your actual PublicWWW/OpenRouter account limits — these are account-specific numbers this document can't supply for you.
- Confirm PublicWWW account/API tier and rate limits before relying on it for real signature-search volume, and decide the Part 5 ingestion cadence (continuous scrape vs. a periodic scheduled run) — this now also affects Part 6.1's cadence and the `provider_budgets` figure above, since both consume the same quota.
- Fill in the shoe-photo-upgrade and WP-remediation business briefs (§0.3) with your actual service name/pricing before flipping their `campaigns.status` from `draft` to `active` and running Stage 1 for those campaigns.
- Rotate any API key that was ever pasted into a chat window; confirm Firecrawl auth is actually on before any campaign runs for real.
- Confirm self-hosted Firecrawl's feature parity (JS rendering, PDF text extraction) against the actual deployed instance before Part 3 relies on it for JENEX's PDF catalogs.
