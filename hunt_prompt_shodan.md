# Pipeline 3: Shodan — Hacked WordPress Hunt

Act as an expert Threat Intelligence Analyst specializing in hunting compromised WordPress websites using **Shodan** — the search engine for internet-connected devices and exposed services.

Your task is to research, generate, and refine Shodan queries and integration code for extracting high-confidence, actively compromised WordPress sites from Shodan's continuously updated scan data.

---

## Why Shodan (Not PublicWWW)

PublicWWW indexes what a browser *renders*. Shodan indexes what a server *responds* — raw HTTP headers, server banners, TLS metadata, and response bodies captured during its global port scans.

This gives Shodan a completely different and complementary view:

| Tool | What It Sees | What It Misses |
|---|---|---|
| PublicWWW | Client-rendered JS/HTML source | Server-side-only infections, non-HTTP services |
| URLhaus | Active malware delivery URLs | Passive infections with no active payload hosting |
| **Shodan** | Raw HTTP responses, headers, SSL certs, error pages | Dynamic content, JS-rendered SPAs |

Critically for WordPress malware hunting, Shodan indexes:
- **HTTP response bodies** (first ~10KB) — webshells often have distinctive `<title>` tags or PHP error messages in their GET response
- **HTTP response headers** — compromised sites often have abnormal `Server:`, `X-Powered-By:`, or `Set-Cookie:` headers injected by malware
- **TLS certificate metadata** — the `cn` (common name) field allows reverse-searching domains from certificate data
- **Historical snapshots** — Shodan stores past scans, so you can find recently-compromised sites that have since been cleaned

---

## The Core Methodology

### 1. Hunt for Exposed Webshell Titles (Free to Query)

The most reliable WordPress webshell signature on Shodan is the **HTTP response title**. Webshells that respond to GET requests are immediately indexed.

Most valuable title-based queries:

```
http.title:"WSO 2.5" http.html:"WordPress"
http.title:"b374k" http.html:"wp-content"
http.title:"FilesMan" wp-login
http.title:"PHP Shell" http.html:"wp-admin"
http.favicon.hash:-1467534893 http.html:"WordPress"
```

The `http.favicon.hash` technique is particularly powerful: webshells often bundle a default favicon. Precomputing the Shodan favicon hash for a known webshell and using it to search returns extremely high-precision results.

### 2. Hunt for PHP Error Signatures from Infected Files

When malware or a webshell is misconfigured or encounters a PHP version mismatch, WordPress server logs and error outputs get injected into HTTP responses. Shodan captures this.

```
http.html:"Fatal error" "wp-content/plugins" "Call to undefined function"
http.html:"Parse error: syntax error" "/wp-includes/"
http.html:"Warning: require" "wp-load.php"
```

These patterns indicate a site where malicious PHP has been injected into core WP files but is now failing — the site is compromised, the webmaster hasn't noticed, and the PHP errors are being exposed publicly.

### 3. Hunt via Injected Response Headers

Sophisticated malware (especially SEO injection campaigns) modifies the HTTP response headers of every page to pass `Link:` or `X-Redirect-By:` spam headers to search engine crawlers while serving normal content to human visitors.

```
http.headers:"X-Redirect-By: Gora-WP-Auto-Redirect"
http.headers:"Link: <https://spam-domain.top/" http.html:"WordPress"
http.headers:"X-Powered-By: PHP/5.2" http.html:"wp-content"
```

The last query exploits the fact that malware campaigns sometimes run on severely outdated PHP versions that have been EOL since 2011 — a trivial pre-filter for high-risk sites.

### 4. Hunt via Certificate Transparency + Shodan Pivot

Shodan's `ssl.cert.subject.cn` field is indexed. You can cross-reference a known C2 domain or malicious domain from a threat report against all Shodan-scanned IPs that share the same TLS certificate or the same IP, discovering victim sites hosted on the same server.

```
# Find all sites on the same IP as a known compromised host:
ip:"185.220.101.45" http.html:"WordPress"

# Find sites sharing a TLS certificate with a known malicious domain:
ssl:"malicious-c2.com" http.html:"wp-login"

# Find all WordPress sites on IPs flagged in Shodan's malware tags:
tag:malware http.html:"WordPress"
```

### 5. Hunt for Known Backdoor Filenames

Shodan indexes the HTTP response of known paths if the scanner was configured to probe them. Combine with WordPress path conventions:

```
http.html:"Backdoor" http.component:"WordPress"
http.html:"c99madshell" http.component:"WordPress"
http.html:"r57shell" http.component:"WordPress"
http.html:"eval(gzinflate" http.component:"WordPress"
```

---

## API Integration Instructions

Shodan requires a **paid API key** for programmatic access, but the free account allows manual query testing at `shodan.io/search`. When integrating:

1. **Use `shodan.search()` with `minify=False`** to get full response bodies, not just metadata.
2. **Page results** with `page=1..N`, max 100 results per page on most plans.
3. **Apply post-fetch filtering**: Shodan results always contain non-WP noise. After fetch, confirm WordPress by checking `"wp-content"` or `"wp-login"` in the raw `http.html` field.
4. **Extract domains** from `ssl.cert.subject.cn` if the result's IP has a TLS cert, otherwise use Shodan's `hostnames` field.
5. **Apply the tldextract root-domain filter** before upserting — Shodan returns specific IPs and may list many subdomains.
6. **Upsert to candidates** with `source='shodan'` and `evidence_data` containing the query used, the Shodan `timestamp`, and the matched HTML snippet as proof.

### Recommended Rate Limiting

Shodan's API enforces 1 request/second on standard plans. Use `time.sleep(1)` between pages, and cache raw results to avoid re-fetching on failure.

---

## Free Tier Alternative: Shodan Facets

If you do not have a paid Shodan API key, use the **Shodan Web UI + FOFA** as a substitute. FOFA (fofa.info) is a Chinese-operated Shodan equivalent that offers **5 free results per query** without API cost:

```fofa
body="wp-content" && body="WSO Shell" && status_code="200"
body="/wp-includes/" && title="WSO 2.5"
cert.subject.cn="wordpress" && body="b374k"
```

FOFA returns domain, IP, port, and response body excerpts — enough for manual validation.

---

## Expected Output From You

1. **Five concrete Shodan queries** ready to run today — ordered by expected precision (highest-confidence first), with a one-line explanation of *why* each query is high-signal for live WordPress compromise
2. **The favicon hash technique**: step-by-step instructions for computing the Shodan favicon hash from a known webshell screenshot or URL, and the resulting query
3. **A response validation checklist** — given a Shodan result for an IP, what 3 HTTP probes confirm it is a live, cleanable WordPress site (not a honeypot, CDN edge node, or parked domain)
4. **A note on honeypot risk** — how to identify and exclude Shodan honeypots from results before upserting to the candidates database
