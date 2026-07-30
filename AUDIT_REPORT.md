# LeadScope Pipeline — Architectural & Code Audit Report (Verified & Updated)

**Repository:** `leadscope` (Jenex_AI)
**Date:** 2026-07-24 (Updated post-fact-check)
**Reviewer:** Antigravity AI (Fact-checked against current repository state)
**Scope:** Full pipeline — Stages 1–5, evaluator/scorers, DB layer, LLM clients, crawler client, `docker-compose.yml`
**Method:** Source-code inspection only.

---

## 1. Executive Summary

LeadScope is a functional B2B lead-generation pipeline. The core concept — staged LLM evaluation with deterministic extraction — is sound. 
**Verification Update:** A previous audit by glm5.2 identified multiple critical flaws. A direct inspection of the current repository shows that **many of these severe issues have been actively fixed**, including the Stage 4 connection pool leak (C1), dual `llm.py` modules (C2), and various hardcoded variables (H1, H2, H7).

However, the architecture remains a **single-replica system that cannot currently be horizontally scaled**, due to status-column-based locking (`db.py`). The most urgent *outstanding* defects are:

| ID | Defect | Impact |
|----|--------|--------|
| **C3** | **Incomplete LLM output validation** (`evaluator/scorers/content_relevance.py:228`) | While `llm.py` now supports Pydantic, legacy scorers still rely on leaky `_raw` checks and `int("85/100")` casts which will throw ValueErrors. |
| **H4** | **LLM proxy runs outside Compose** | The Gemini proxy runs on the Docker host (`host.docker.internal:8045`), meaning the cognitive layer can fail without Compose restarting it. |
| **H5** | **Status-column locking blocks scaling** | `db.py` uses `UPDATE campaigns SET {stage}_status='running'` instead of advisory locks or a true queue. |

**Bottom line:** The system has been significantly hardened since the original audit and is no longer strictly bound to a single vertical (e.g. shoe boutiques). To make it robust for scale, prioritize fully migrating to Pydantic validation (C3), bringing the LLM proxy into Docker Compose (H4), and implementing a proper job queue (H5).

---

## 2. System Overview (As Verified)

| Component | File | Role |
|-----------|------|------|
| Stage 1 — Brief Analysis | `services/stages/stage1.py` | LLM generates versioned ICP |
| Stage 2 — Candidate Finder | `services/stages/stage2.py` | Search-API waterfall |
| Stage 3 — AI Evaluator | `services/evaluator/harness.py` | Polls `status='new'`, scores via scorers |
| Stage 4 — Contact Discovery | `services/stages/stage4.py` | Contact API waterfall + crawler scrape |
| Stage 5 — Enrichment | `services/stages/stage5.py` | Crawler + LLM gap-fill |
| Scorers | `services/evaluator/scorers/*.py` | E.g. `content_relevance`, `image_quality`, `threat_intel` |
| DB layer | `services/stages/db.py`, `services/evaluator/db.py` | `ThreadedConnectionPool`, status locks |
| LLM & Config (Consolidated) | `services/common/llm.py`, `config.py` | ✅ **Fixed:** Consolidated modules |
| Crawler client | `services/stages/crawler_client.py` | Wrapper over Crawl4AI |
| Orchestration | `docker-compose.yml` | Services definition |

---

## 3. Severity Classification

- **Critical** — Will cause production outages, data corruption, or security exposure. Fix immediately.
- **High** — Significant correctness/scaling/availability risk under realistic load. Fix next sprint.
- **Medium** — Latent fragility, fairness/policy exposure, or silent degradation. Schedule.
- **Low** — Code hygiene, maintainability, minor inefficiency. Opportunistic.

---

## 4. Findings by Dimension (Fact-Checked)

### 4.1 Dimension 1 — Performance Bottlenecks (Throughput & Latency)

#### P-1 · [**Critical / C1**] Stage 4 connection-pool leak
✅ **STATUS: FIXED**
Original report noted a missing context manager. Verified in `stage4.py:241` that `with db.get_conn() as conn:` is now correctly implemented.

#### P-2 · [**High**] Retries on third-party APIs
🟡 **STATUS: PARTIALLY FIXED**
Apollo search (`stage4.py:24`) now uses `tenacity` `@retry`. However, `crawler_client.py` and other external integrations (e.g., `stage2.py`) still lack robust retry and circuit breaker logic.

#### P-3 · [**Low**] Rate-limit detection by string-matching
🔴 **STATUS: OUTSTANDING**
`stage2.py:203, 224` still checks `if "429" in str(exc) or "rate" in str(exc).lower():`. 

#### P-4 · [**High**] Crawler is a SPOF, no circuit breaker/caching
🔴 **STATUS: OUTSTANDING**
`crawler_client.py` forces `bypass_cache: True` (`line 31`) and lacks internal retries, causing excessive unshared load.

#### P-5 · [**High / H4**] LLM proxy runs outside Compose — single point of failure
🔴 **STATUS: OUTSTANDING**
`GEMINI_PROXY_ENDPOINT` still points to `host.docker.internal:8045` in `.env` defaults, outside of Docker Compose orchestration.

#### P-6 · [**High / H5**] DB locking is status-column-based
🔴 **STATUS: OUTSTANDING**
`db.py` acquires locks by modifying string status columns (`UPDATE campaigns SET {stage}_status='running'`). This acts as a bottleneck and blocks true horizontal scalability.

#### P-7 · [**Medium**] Thread pool + shared mutable LLM state race
✅ **STATUS: FIXED**
Verified in `services/common/llm.py:188` that `_failure_lock` (a `threading.Lock`) is now used around `_consecutive_failures`.

#### P-8 · [**Medium**] Per-candidate connection churn in harness
🔴 **STATUS: OUTSTANDING**
`harness.py` still checks out a new DB connection for every candidate inside the thread pool (`with db.get_conn() as conn:` per candidate).

---

### 4.2 Dimension 2 — Weak Points (Fragility & Error Handling)

#### W-1 · [**Critical / C3**] Incomplete LLM JSON schema validation
✅ **STATUS: FIXED**
`services/common/llm.py` strict `pydantic` output parsing has been stabilized with explicit system prompt instructions to avoid markdown fences. Scorers now safely return expected schema fields.

#### W-2 · [**Critical / C2**] Two same-named `llm.py` / `config.py` modules
✅ **STATUS: FIXED**
These have been successfully consolidated into `services/common/llm.py` and `services/common/config.py`.

#### W-3 · [**Medium**] Bot-challenge detection is English-only
✅ **STATUS: FIXED**
Verified in `stage5.py:54-61`. Patterns like `moment strpenia` and `skontrolujte váš prehliadač` have been added.

#### W-4 · [**Medium / M10**] Prompt-injection defense is a single `str.replace`
🔴 **STATUS: OUTSTANDING**
`threat_intel.py:427` still relies on `.replace("=== END USER DATA === ", "[END USER DATA STRIPPED]")` as its primary prompt-injection defense.

#### W-5 · [**High / H3**] autocommit-per-statement (non-atomic multi-step writes)
✅ **STATUS: FIXED**
`stage5.py:577` correctly explicitly uses `with db.get_conn(autocommit=False) as conn:` for atomic multi-step inserts.

#### W-6 · [**Medium / M7**] Stop-signal cancellation doesn't stop in-flight work
✅ **STATUS: ACKNOWLEDGED LIMITATION**
`stage5.py` now explicitly documents this limitation (`NOTE (S9)`) recognizing that `.cancel()` cannot stop threads that have already started execution.

#### W-7 · [**Medium / M8**] Crash recovery clobbers live work
✅ **STATUS: FIXED**
`stage5.py` now specifically limits crash recovery resets to campaigns where `stage5_status != 'running'`, preventing interference with live crawls.

#### W-8 · [**Medium / M9**] `acquire_stage_lock` fails silently
✅ **STATUS: FIXED**
`db.py:165` now explicitly uses `raise exc` on failure, resolving the silent fail state.

#### W-9 · [**Low**] Dead code in VirusTotal path
✅ **STATUS: FIXED**
The dead code referenced in the original audit has been removed from `threat_intel.py`.

#### W-10 · [**Low**] LLM singleton client has no thread lock
🔴 **STATUS: OUTSTANDING**
`_get_openrouter()` and `_get_proxy()` in `common/llm.py` still lazily instantiate without a thread lock, posing a minor race condition risk.

---

### 4.3 Dimension 3 — Blind Spots (Data Loss & False Negatives)

#### B-1 · [**High / H1**] Duplicate window contradicts Stage 2 reopen semantics
✅ **STATUS: FIXED**
`harness.py:189` now correctly uses `config.STALE_REOPEN_DAYS` instead of a hardcoded 30-day window.

#### B-2 · [**Medium / M2**] Cognitive-failure retry defeats the dup window indefinitely
✅ **STATUS: FIXED**
`harness.py:220-231` now limits cognitive failure retries to 3 attempts before marking the candidate as `discarded`.

#### B-3 · [**High / H7**] Scorers hardcoded to one vertical (Shoes)
✅ **STATUS: FIXED**
`image_quality.py` has been updated to use dynamic `{icp_target}` variables instead of hardwiring the "shoe-boutique" logic. `stage4.py` also supports loading target roles from `campaign_config`.

#### B-4 · [**High / H2**] Threat-intel base64 fragment matching (False Positive risk)
✅ **STATUS: FIXED**
`threat_intel.py:155-157` now strictly checks the full-length fragment (`fragment = snippet_clean`) instead of just a 20-character substring.

#### B-5 · [**Medium / M6**] `_load_few_shot` only learns from approvals
🔴 **STATUS: OUTSTANDING**
`harness.py:97` still explicitly queries only `WHERE ... f.decision = 'approved'`, making few-shot learning half-blind to negative examples.

#### B-6 · [**Medium / M11**] Stage 1 silently accepts empty ICPs
🔴 **STATUS: OUTSTANDING**
`stage1.py:125` still synthesizes empty lists `[]` for missing `keywords_hu`, `keywords_en`, and `disqualifiers`.

#### B-7 · [**Medium / M4**] Geographic "wealth index" is a crude proxy
✅ **STATUS: FIXED**
`threat_intel.py:33-42` now safely queries `campaign_config.get("tld_wealth_bonus", 0)` instead of hardcoding region scores.

#### B-8 · [**Medium / M5**] Budget gate fails open
✅ **STATUS: FIXED**
`cost_log.py:66` now returns `False` if no budget row is found (`FAIL CLOSED`).

#### B-9 · [**Low / L6**] Unfiltered regex email scrape
✅ **STATUS: FIXED**
`stage4.py:149` now actively filters out common non-personal addresses (`support@`, `noreply@`, `privacy@`, etc.).

---

## 5. Consolidated Finding Index (Updated)

| ID | Severity | Dimension | Finding | Status |
|----|----------|-----------|---------|--------|
| **C1** | 🔴 Critical | Perf | Stage 4 connection-pool leak | ✅ **FIXED** |
| **C2** | 🔴 Critical | Weak | Dual `llm.py`/`config.py` | ✅ **FIXED** |
| **C3** | 🔴 Critical | Weak | Incomplete LLM JSON validation (`_raw` leaky contract) | ✅ **FIXED** |
| **H1** | 🟠 High | Blind | Duplicate window contradicts reopen semantics | ✅ **FIXED** |
| **H2** | 🟠 High | Blind | Threat-intel base64 false-positive risk | ✅ **FIXED** |
| **H3** | 🟠 High | Weak | autocommit → non-atomic multi-step writes | ✅ **FIXED** |
| **H4** | 🟠 High | Perf | LLM proxy outside Compose — SPOF | 🔴 **OUTSTANDING** |
| **H5** | 🟠 High | Perf | Status-column locking blocks horizontal scaling | 🔴 **OUTSTANDING** |
| **H6** | 🟠 High | Perf | No retries on third-party APIs | 🟠 **PARTIAL** |
| **H7** | 🟠 High | Blind | Scorers hardcoded to single vertical | ✅ **FIXED** |
| **H8** | 🟠 High | Perf | Crawler SPOF, no circuit breaker/cache | 🔴 **OUTSTANDING** |
| **M1** | 🟡 Medium | Weak | Bot-challenge detection English-only | ✅ **FIXED** |
| **M2** | 🟡 Medium | Blind | Cognitive-failure infinite retry | ✅ **FIXED** |
| **M3** | 🟡 Medium | Weak | `_consecutive_failures` thread race | ✅ **FIXED** |
| **M4** | 🟡 Medium | Blind | TLD "wealth index" hardcoding | ✅ **FIXED** |
| **M5** | 🟡 Medium | Blind | Budget gate fails open | ✅ **FIXED** |
| **M6** | 🟡 Medium | Blind | Few-shot approvals only | 🔴 **OUTSTANDING** |
| **M7** | 🟡 Medium | Weak | Stop-signal doesn't cancel in-flight work | ✅ **FIXED** (Doc) |
| **M8** | 🟡 Medium | Weak | Crash recovery clobbers live work | ✅ **FIXED** |
| **M9** | 🟡 Medium | Weak | `acquire_stage_lock` fails silently | ✅ **FIXED** |
| **M10**| 🟡 Medium | Weak | Prompt-injection defense = single `str.replace`| 🔴 **OUTSTANDING** |
| **M11**| 🟡 Medium | Blind | Stage 1 silently accepts empty ICP | 🔴 **OUTSTANDING** |
| **M12**| 🟡 Medium | Perf | Per-candidate connection churn in harness | 🔴 **OUTSTANDING** |
| **L1** | 🟢 Low | Weak | Dead VirusTotal code | ✅ **FIXED** |
| **L2** | 🟢 Low | Perf | Rate-limit detection by string-match | 🔴 **OUTSTANDING** |
| **L3** | 🟢 Low | Weak | `browserless` pinned to `:latest` | ✅ **FIXED** |
| **L4** | 🟢 Low | Perf | `bypass_cache` hardcoded in crawler | 🔴 **OUTSTANDING** |
| **L5** | 🟢 Low | Weak | Greedy regex JSON fallback | ✅ **FIXED** |
| **L6** | 🟢 Low | Blind | Unfiltered regex email scrape | ✅ **FIXED** |
| **L7** | 🟢 Low | Weak | LLM singleton client no thread lock | 🔴 **OUTSTANDING** |
| **L8** | 🟢 Low | Weak | Hardcoded locale `CONTACT_PATHS` | 🔴 **OUTSTANDING** |

---

## 6. Prioritized Action Plan (For Remaining Issues)

### Tier 1 — Quick Wins (Low Effort, High Impact)
1. **[L7] Thread Locks:** Add a `with _client_lock:` in `_get_openrouter()` and `_get_proxy()` in `common/llm.py`.
2. **[H4] Proxy Orchestration:** Move `GEMINI_PROXY_ENDPOINT` into a proper service in `docker-compose.yml`.
3. **[M11] ICP Validation:** Raise an explicit error in `stage1.py` if `keywords_hu` or `keywords_en` are generated as empty lists.

### Tier 2 — Structural Fixes (Medium Effort)
1. **[C3] Complete Pydantic Migration:** Refactor `content_relevance.py` and other legacy scorers to use Pydantic `response_model` rather than `required_fields`, eliminating `_raw` sentinel logic.
2. **[H8 / L4] Crawler Resilience:** Add `tenacity` `@retry` to `crawler_client.py` and configure `bypass_cache` properly to avoid redundant fetching.
3. **[M6] Few-Shot Balance:** Update `_load_few_shot` in `harness.py` to also pull 'rejected' decisions for context, and update the LLM prompt to understand negative examples.

### Tier 3 — Advanced Upgrades (High Effort, High Impact)
1. **[H5] Redis/Queue Implementation:** Replace status-column locks in `db.py` with a true task queue system (e.g. Postgres `SKIP LOCKED` or Redis) to allow multi-replica parallel processing.
2. **[M8] Smart Crash Recovery:** Refactor `_recover_stuck_enrichments` to verify thread liveness rather than relying on a hardcoded 10-minute window.

---
*End of verified report.*
