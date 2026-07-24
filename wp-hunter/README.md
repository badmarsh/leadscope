# WordPress Compromise Hunting Pipeline

Passive OSINT discovery of compromised WordPress sites using published IOCs.

## Features
- **Passive Recon Only**: Read-only OSINT analysis, no target interaction/exploitation.
- **Stage A (Ingest)**: Parse PublicWWW CSV exports or text pastes, handling domain redactions (`visible: false`).
- **Stage B (Pivot)**: Query urlscan.io Search API and VirusTotal API v3 (hashes & domains).
- **Stage C (Report)**: Produce flat CSV, grouped Markdown with confidence breakdown, and structured JSON reports.
- **Stage D (Freshness Gate)**: Operationalize IOC expiration against `stale_after_days`.

## Setup
```bash
pip install -e .
```

Copy `.env.example` to `.env` and fill in `URLSCAN_API_KEY` and `VT_API_KEY`.

## Usage
```bash
# Ingest PublicWWW export for a campaign
python -m wp_hunter.cli ingest --campaign socgholish-ndsw --file export.csv

# Pivot via urlscan / VirusTotal
python -m wp_hunter.cli pivot --campaign socgholish-ndsw

# Generate reports
python -m wp_hunter.cli report

# Full one-shot run
python -m wp_hunter.cli run --campaign socgholish-ndsw --file export.csv
```
