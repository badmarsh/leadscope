# Contributing to LeadScope

## Development Setup

```bash
# Clone and install
git clone https://github.com/badmarsh/leadscope
cd leadscope
cp .env.example .env    # fill in your API keys
pnpm install

# Start local infrastructure
docker compose up -d postgres
pnpm dev
```

## Before Submitting a PR

1. **All tests must pass:**
   ```bash
   pnpm test                  # Vitest TypeScript tests
   pytest tests/unit/ tests/integration/   # Python tests
   pnpm test:e2e              # Playwright browser tests (requires dev server)
   ```

2. **Lint must pass:**
   ```bash
   pnpm run lint
   ```

3. **No scratch files** in the project root — put them in `scripts/` or omit from commit.

4. **New environment variables** must be documented in `.env.example`.

5. **Database schema changes** must include an Alembic migration in `db/migrations/versions/`.

## Repository Structure

| Path | Purpose |
|---|---|
| `app/api/` | Next.js API route handlers (thin — delegates logic to `lib/`) |
| `lib/` | Shared TypeScript utilities, hooks, DB access, LLM client |
| `components/` | React components (UI rendering only) |
| `locales/` | i18n translation strings (`en.json`, `sk.json`) |
| `services/stages/` | Python pipeline microservice (Stage 1, 2, 5) |
| `services/evaluator/` | Python scoring microservice (Stage 3) |
| `db/` | Schema, seed data, and Alembic migrations |
| `scripts/` | Developer utility scripts (not tested in CI) |
| `tests/unit/` | Vitest and pytest unit tests |
| `tests/integration/` | pytest integration tests (requires Postgres) |
| `tests/e2e/` | Playwright E2E browser tests |
| `.agents/` | AI coding prompts and system references |
