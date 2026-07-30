# LeadScope Unified Audit & Task Backlog

Curated backlog of actionable tasks. Items already completed or not recommended have been pruned. Ordered by priority (🔴 Critical → 🟡 Medium → 🟢 Nice-to-have).

---

## 🔴 Critical — Hardening & Operational Fixes

### 1. Horizontal Scaling: Replace Status-Column Locks ✅ Done
**Origin:** Ops Audit (Phase 3)  
**Implementation:** Updated `acquire_stage_lock` and `release_stage_lock` in `services/stages/db.py` to use Postgres `pg_try_advisory_lock` advisory locks for multi-replica concurrency.

### 2. SSRF Filter Hardening (IPv6 + DNS Rebinding)
**Origin:** Phase 4 Audit  
**Implementation:** Added server-side DNS resolution (`dns.promises.lookup`) and expanded IP blocklist regexes in `app/api/screenshot/route.ts` to cover IPv6 loopbacks, mapped IPv4, and internal CIDRs.

### 3. Crawler Resilience (Retries + Caching) ✅ Done
**Origin:** Ops Audit (Phase 3, Issue H8)  
**Implementation:** Added `tenacity` retry decorator (3 attempts, exponential backoff) to `crawler_client.py`.

---

## 🟡 Medium — Hardening & Polish

### 4. Prompt Injection Defense (Stage 3/5 Extraction) ✅ Done
**Origin:** Ops Audit (Phase 3, Issue M10)  
**Implementation:** Sandboxed scraped website text in `<website_content>` tags and added strict safety instructions to LLM prompts in `services/stages/stage5.py`.

### 5. Rerun Race Condition Guard ✅ Done
**Origin:** Phase 4 Audit  
**What:** If a user clicks "Rerun Evaluation" while a Stage 3 background worker is actively processing that candidate, both processes write conflicting results.  
**Recommendation:** Add `SELECT ... FOR UPDATE SKIP LOCKED` on the candidate row before starting evaluation. If the row is locked, the rerun request returns a "currently processing" status instead of racing.  
**Files:** `services/evaluator/harness.py`, `app/api/candidates/rerun/route.ts`

### 6. README Documentation Drift (n8n References) ✅ Done
**Origin:** Phase 2  
**Implementation:** Updated `README.md` and `docker-compose.yml` to purge legacy n8n references and replace them with FastAPI microservice cron triggers.

### 7. LLM Proxy into Docker Compose
**Origin:** Phase 1  
**What:** The Gemini LLM proxy runs outside Docker Compose as a standalone process on `host.docker.internal:8045`. If it crashes, nothing auto-restarts it.  
**Recommendation:** Add a `gemini-proxy` service to `docker-compose.yml` with `restart: unless-stopped` and health checks.  
**Files:** `docker-compose.yml`

---

## 🟢 Nice-to-Have — When Time Permits

### 8. Fallback Company Name Extraction ✅ Done
**Origin:** Phase 4  
**What:** When the LLM fails to extract a company name during Stage 5, it falls back to the raw domain (e.g., `swapboutique.com`). This looks unprofessional in exports.  
**Recommendation:** Before falling back to domain, try extracting from `<title>` tag, Open Graph `og:site_name`, or Schema.org `Organization.name` from the scraped metadata. Only fall back to domain as a last resort.  
**Files:** `services/stages/stage5.py`

### 9. PublicWWW Budget Gate Verification
**Origin:** Phase 2  
**What:** The `provider_budgets` config is supposed to cap PublicWWW API spending, but it's unclear if the gate actually blocks queries when the cap is reached.  
**Recommendation:** Write an integration test that sets a budget of 0 and verifies that the scraper raises/skips instead of executing.  
**Files:** `services/stages/publicwww_scraper.py`, `services/stages/tests/`

### 10. PublicWWW Query Refinement (Narrow IOCs)
**Origin:** Phase 5  
**What:** Generic PHP signatures in PublicWWW queries produce noisy results.  
**Recommendation:** Refine queries to use narrow, unique, and fresh IOCs (e.g., specific JS variables like `ndsw===undefined` or unique C2 domain strings). Use `depth:all` and `snipexp:|regex|` for extraction.  
**Files:** `wp-hunter/campaigns.yaml`, `seo-spam-hunter/campaigns.yaml`

---

## ❌ Removed (Not Recommended)

The following items were present in the original megaprompt but have been pruned:

| Item | Reason for Removal |
|---|---|
| n8n Orchestration | Intentionally abandoned. FastAPI is simpler and working. |
| Advanced VT Graph Walking | High API cost, low ROI for current scale. Manual pivots suffice. |
| Shodan Pipeline Integration | Adds operational complexity and a paid API dependency for marginal threat coverage gain. Not worth it until the core pipeline is fully hardened. |
| URLhaus CSV Ingestion | `urlhaus_monitor.py` job already handles this feed. Building a second ingestion path is redundant. |
| Few-Shot Learning Bias (M6) | Already fixed — `_load_few_shot` now pulls both approved and rejected decisions. |
| CSV Formula Injection | Already fixed — `csvField()` in export route sanitizes `=`, `+`, `-`, `@`, `\t`, `\r`. |
| External Red Team Audit | This is a process step, not a code task. Can be done anytime by pasting the existing `gpt_audit_and_weakpoint_prompt.md` into a frontier LLM. |
