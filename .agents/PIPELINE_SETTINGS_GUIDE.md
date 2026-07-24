# Jenex AI Pipeline Settings Guide

This document explains the various configuration options and toggles available across the Jenex AI pipelines (Leadscope, WP Hunter, SEO Spam Hunter, and Threat Intel).

## 1. Core Lead Generation (leadscope)
Located in `campaigns.yaml` (root) and `lib/leads-data.ts`.

- `id`: The unique identifier for the campaign (e.g., `jenex`, `shoe-photo`, `wp-remediation`). Must match exactly across tools.
- `evaluator`: The Python scorer script to use in Stage 3 (`image_quality` or `threat_intel`).
- `status`: Used in `lib/leads-data.ts` to determine if a pipeline is `active`, `paused`, or `draft` on the dashboard UI.

## 2. WP Compromise Hunter (`wp-hunter/campaigns.yaml`)
Targeted at discovering WordPress sites infected with specific malware families.

- `stale_after_days`: Controls the Stage D Freshness Gate. If the campaign's `added` date is older than this value, the pipeline refuses to run (to prevent burning API credits on old IOCs) unless bypassed via `--i-know-this-is-stale`.
- `publicwww_query`: The exact search query sent to PublicWWW to find infected sites based on source code snippets.
- `fit`: If set to `not_suitable_for_publicwww`, the pipeline skips Stage A (PublicWWW ingest) entirely. Used for server-side backdoors.
- `urlscan_pivot`: A list of search queries to run against URLScan.io's historical index (e.g., searching for specific filenames or injected code).
- `virustotal_pivot`: 
  - `hashes`: SHA-256 hashes of known malware payloads to search for communicating domains.
  - `domains`: Known C2 domains to pivot from.
- `--vt-graph`: A CLI toggle (default: `False`). If enabled, walks the VirusTotal relationship graph (e.g., finding domains resolving to the same malicious IPs).

## 3. SEO Spam & Backdoor Hunter (`seo-spam-hunter/campaigns.yaml`)
Targeted at discovering SEO spam injections (e.g., Japanese Keyword Hack, Pharma Hack).

- `wayback_pivot`:
  - `enabled`: Toggle for Archive.org CDX pivot. (Default: `false` due to high performance costs and rate limits).
  - `match_mime`: Only look at historical snapshots matching this MIME type (e.g., `text/html`).
- `location`: Metadata indicating where the spam is typically found (`html_body`, `server_side`).

## 4. Threat Intel Feeds (`services/jobs/certstream_monitor.py`)
Real-time Certificate Transparency log monitoring.

- `HIGH_VALUE_TLDS`: A Python set of target top-level domains (e.g., `.com`, `.sk`, `.hu`). Domains not ending in these are instantly dropped to save processing power.
- `EXCLUDED_DOMAINS`: A blocklist of hosting providers, CDNs, and platforms (e.g., `cloudflare.com`, `amazonaws.com`) to filter out noise.

## Pipeline Flow & Freshness Gate
Both WP Hunter and SEO Spam Hunter implement a **Freshness Gate**.
- If a campaign template contains the string `{{`, the pipeline will automatically block execution to prevent running unfinished templates.
- If the current date is past `added + stale_after_days`, execution is blocked to preserve API credits.
