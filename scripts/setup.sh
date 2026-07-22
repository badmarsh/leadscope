#!/usr/bin/env bash
# scripts/setup.sh — One-command local dev environment setup
set -euo pipefail

echo "▶ Copying .env.example → .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  ✓ .env created — fill in your API keys before running docker compose"
else
  echo "  ✓ .env already exists"
fi

echo "▶ Installing Node.js dependencies"
pnpm install

echo "▶ Starting Docker services"
docker compose up -d postgres n8n

echo "▶ Waiting for PostgreSQL..."
until docker compose exec postgres pg_isready -U leadscope; do sleep 1; done

echo "▶ Applying database schema"
docker compose exec -T postgres psql -U leadscope leadscope < db/schema.sql

echo "▶ Applying seed data"
if [ -f db/seed.sql ]; then
  docker compose exec -T postgres psql -U leadscope leadscope < db/seed.sql
fi

echo ""
echo "✅ Setup complete. Run: pnpm dev"
