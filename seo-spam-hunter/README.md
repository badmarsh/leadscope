# Advanced WordPress SEO Spam & Backdoor Hunting Pipeline

Passive OSINT discovery of compromised WordPress sites infected with SEO spam, link farms, and backdoors.

## Features
- **Passive Recon Only**: Read-only OSINT analysis, no target interaction/exploitation.
- **Stage A (Ingest)**: Parse PublicWWW CSV exports or text pastes, handling domain redactions (`visible: false`).
- **Stage B (Pivot)**: Query urlscan.io Search API, VirusTotal API v3, and **Wayback Machine CDX API**.
- **Stage C (Report)**: Produce flat CSV, Markdown (with confidence and clusters), JSON, and Edge List for Graph software.
- **Stage D (Freshness Gate)**: Operationalize IOC expiration against `stale_after_days`.
- **Stage E (Clustering)**: Map out SEO spam link farms via `domHash`, `ASN`, and `IP` similarities using `networkx`.

## Setup
```bash
pip install -e .
```

Copy `.env.example` to `.env` and fill in `URLSCAN_API_KEY` and `VT_API_KEY`.

## Usage
```bash
# Full one-shot run with clustering and wayback history enabled
python -m seo_spam_hunter.cli run --campaign japanese-keyword-hack --file export.csv --cluster --wayback
```
