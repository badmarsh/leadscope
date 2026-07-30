# LeadScope Platform

A high-performance lead generation, evaluation, and AI-powered intelligence platform built with Next.js 16 (App Router), PostgreSQL, microservices, and Docker.

---

## 🏛️ System Architecture

```
                       ┌─────────────────────────┐
                       │   Next.js 16 Dashboard  │
                       │  (App Router + Tailwind)│
                       └────────────┬────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │   iron-session Auth │
                         └──────────┬──────────┘
                                    │
    ┌──────────────────────┬────────┴─────────────┬──────────────────────┐
    │                      │                      │                      │
┌───▼───────────────┐  ┌───▼───────────────┐  ┌───▼───────────────┐  ┌───▼───────────────┐
│ PostgreSQL DB     │  │ Evaluator Service │  │ Stages Service    │  │ Crawler Service   │
│ (leadscope pool)  │  │ (Shared llm.py)   │  │ (Shared llm.py)   │  │ (Crawl4AI)        │
└─────────▲─────────┘  └───────────────────┘  └───────────────────┘  └───────────────────┘
          │
   ┌──────┴─────────────────────────────────┐
   │ Background Jobs & Orchestration        │
   │ - n8n (crons for core pipeline)        │
   │ - certstream_monitor (HTTP / DB queues)│
   │ - malwarebazaar / publicwww / hunters  │
   │ - icp_drift_job                        │
   └────────────────────────────────────────┘
```

---

## 🚀 Quick Start & Local Setup

### Prerequisites
- Node.js 22+
- pnpm 9+
- Python 3.12+
- Docker & Docker Compose

### Installation & Execution

1. **Environment Setup**:
   ```bash
   cp .env.example .env
   ```

2. **Run Development Server**:
   ```bash
   pnpm install
   pnpm dev
   ```

3. **Run via Docker Compose**:
   ```bash
   docker compose up -d --build
   ```

---

## 🔑 First-Run Auth Setup

Generate the required secrets before starting:

```bash
# 1. Session secret (must be ≥32 characters)
openssl rand -hex 32

# 2. Password hash (replace 'yourpassword' with your actual password)
node -e "const b=require('bcryptjs'); b.hash('yourpassword',12).then(console.log)"
```

Set both values in your `.env` file:
```
DASHBOARD_SESSION_SECRET=<output of step 1>
DASHBOARD_PASSWORD_HASH=<output of step 2>
```

---

## 🗃️ Database Migrations

LeadScope uses [Alembic](https://alembic.sqlalchemy.org/) for schema versioning.

```bash
# Apply all pending migrations
DATABASE_URL=postgresql://... alembic -c db/alembic.ini upgrade head

# On an existing deployment (schema already applied), stamp current state:
DATABASE_URL=postgresql://... alembic -c db/alembic.ini stamp 0001

# Create a new migration after schema changes
DATABASE_URL=postgresql://... alembic -c db/alembic.ini revision --autogenerate -m "describe change"
```

---

## 🌊 Pipeline Stages Reference

| Stage | Name | Trigger | Description |
|---|---|---|---|
| Stage 1 | ICP Definer | Manual / n8n | Generates search queries and target segments from `business_brief` via LLM |
| Stage 2 | Target Finder | n8n cron (every 6h) | Multi-provider search waterfall (Exa → Tavily → Serper → SerpAPI → Brave) → domain candidates |
| Stage 3 | Evaluator | n8n cron | Scores candidates 0–100 against ICP using Firecrawl + Vision AI |
| Stage 5 | Enrichment | n8n cron | Crawl4AI scrape + `extruct` metadata + LLM gap-fill for contact data |

Stage 4 is an intentional numbering gap reserved for human-in-the-loop validation.

---

## 🌍 Multi-Campaign Support

Three campaigns ship by default:

| Slug | Evaluator | Description |
|---|---|---|
| `jenex` | `content_relevance` | HVAC distributor/installer leads in Hungary (Dynamic via ICP) |
| `shoe-photo` | `image_quality` | Visual QA for e-commerce (Dynamic via `{icp_target}`) |
| `wp-remediation` | `threat_intel` | Threat Intel via passive discovery (CertStream, PublicWWW, Hunters) |

To add a new campaign: insert a row into `campaigns`, create an ICP config row, and add the slug → DB ID mapping in `lib/campaigns.ts`.

---

## 🔒 Security Notes

- Single-operator authentication via bcrypt password + iron-session cookie
- Login rate-limited to 5 attempts per 15 minutes per IP
- All API routes validate session server-side before any DB operation
- All SQL queries use parameterized arguments (no string interpolation)
- HTTP security headers (X-Frame-Options, Content-Security-Policy, etc.) applied globally
- No secrets committed — all API keys live in `.env` only

---

## 🧪 Testing Strategy

- **Vitest**: TypeScript unit & component tests (`pnpm test`)
- **pytest**: Python service unit & integration tests (`pytest tests/`)
- **Playwright**: End-to-End browser smoke tests (`pnpm test:e2e`)

```bash
# Run TypeScript Unit Tests
pnpm test

# Run Python Tests
pytest tests/unit/ tests/integration/

# Run E2E Playwright Suite
pnpm test:e2e
```
