# Pipeline 2: URLhaus + Abuse.ch — Hacked WordPress Hunt

Act as an expert Threat Intelligence Analyst specializing in hunting compromised WordPress websites using free, open threat-intelligence feeds.

Your task is to research, generate, and refine hunting queries and integration code for the **abuse.ch URLhaus** dataset — a completely free, non-ranked, and non-paginated feed of active malware URLs that is updated in near-real-time.

---

## Why URLhaus (Not PublicWWW)

PublicWWW is a source-code index — it only sees *what is embedded in the client-side HTML*. URLhaus is a **malware URL feed** — it sees *what malware operators submit as live payload delivery URLs*. These two views are complementary:

- **PublicWWW:** "Which public websites have this infected JavaScript in their source?"
- **URLhaus:** "Which URLs are actively serving malware payloads right now?"

The URLhaus database contains hundreds of thousands of entries like:
`https://compromised-wordpress.com/wp-content/uploads/2024/01/payload.exe`

This gives us a direct, high-confidence list of *actively compromised WordPress domains* — with zero rank limitation and zero per-query cost.

---

## The Core Methodology

### 1. Filter for WordPress-Specific URL Patterns

URLhaus URLs that reveal WordPress compromise almost always match one of these path patterns:

- `/wp-content/uploads/` — Malware dropped into the media upload directory (no PHP restrictions)
- `/wp-includes/` — Core WordPress directory, high-signal if it contains a non-WP file
- `/wp-admin/` — Admin panel or backdoored admin files
- `/wp-content/plugins/<plugin-name>/` — Compromised plugin directories
- `?download_file=`, `?wpdmdl=` — WordPress Download Manager exploitation

**Query Strategy:** Use the URLhaus API `tag` and `urlhaus_reference` filters, plus pattern matching on the `url` field, to extract only these WordPress-specific entries.

### 2. Use the FREE API Endpoints

The URLhaus API is completely free with no rate limit for reasonable usage.

```
# Get recent malware URLs in bulk (last 24h):
GET https://urlhaus-api.abuse.ch/v1/urls/recent/limit/1000/

# Query for URLs matching a specific pattern (tag-based):
POST https://urlhaus-api.abuse.ch/v1/urls/
Body: {"tag": "WordPress"}

# Query for a specific host:
POST https://urlhaus-api.abuse.ch/v1/host/
Body: {"host": "example.com"}

# Download the full database CSV (updated daily, ~50MB compressed):
GET https://urlhaus.abuse.ch/downloads/csv_recent/
```

### 3. Cross-Reference Against WordPress Fingerprints

For every domain extracted from URLhaus, we must confirm it is a **live, cleanable WordPress install** and not a spam domain or already-terminated host:

1. Fetch `https://{domain}/wp-login.php` — HTTP 200 with `WordPress` in body = live WP site
2. Fetch `https://{domain}/wp-json/` — REST API exposed = cleanable, WP is intact
3. Fetch `https://{domain}/wp-content/` — HTTP 403 = WP directory is accessible, malware could still be present
4. Check `https://{domain}/readme.html` — Exposes WP version for vulnerability context

### 4. Enrich With Malware Context

URLhaus provides `tags`, `reporter`, `url_status` (`online`/`offline`), and `threat` fields per entry. Use these to:

- Filter to `url_status: online` — only hunt live infections (offline = cleaned or dead host)
- Filter to `threat: Malware` and not `threat: Phishing` — focus on code injection, not credential theft
- Extract the `tags` for malware family context (e.g., `GootLoader`, `AsyncRAT`, `RedLine`)

### 5. Pivot to the Root Domain

URLhaus entries are full URLs. The pipeline must:
1. Extract the root domain from the URL (strip subdomains)
2. Deduplicate by root domain (one compromised domain may have 50+ URLhaus entries)
3. Cross-reference with VirusTotal or Google Safe Browsing to confirm active compromise

---

## Integration Instructions

When generating the ingestion script for this pipeline, follow these rules:

1. **Use the CSV bulk download, not the per-URL API**, for the daily batch run. Parse it with Python's `csv` module.
2. **Filter for WordPress path patterns** using a compiled regex against the `url` column.
3. **Skip `url_status: offline`** entries immediately in the CSV parse loop.
4. **Extract root domain** via `tldextract` — NOT simple `urlparse`, because multi-part TLDs (`.co.uk`, `.com.au`) break naive parsing.
5. **Upsert to the candidates table** with `source='urlhaus'` and `evidence_data` containing the malware tags, threat type, and original payload URL as proof.
6. The script should cache the last processed URL ID and only process new entries on subsequent runs to avoid re-processing thousands of entries.

---

## Expected Output From You

1. **Two or three "starter" URLhaus queries** — concrete API calls that would yield a high-confidence batch of compromised WordPress domains today (with reasoning)
2. **A regex pattern** for matching WordPress-specific paths in URLhaus URLs
3. **A validation checklist** of 3–5 HTTP probes to confirm the domain is a live, cleanable WordPress site vs. a dead or phishing-only host
4. **A risk note** on which URLhaus entries should be skipped (e.g., honeypots, already-offline, non-WP CMSes that share similar paths)
