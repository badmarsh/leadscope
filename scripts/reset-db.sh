#!/usr/bin/env bash
# scripts/reset-db.sh — Drop and recreate the dev database
set -euo pipefail

echo "⚠️  This will DROP and recreate the leadscope database. Press Ctrl+C to abort."
sleep 3

docker compose exec -T postgres psql -U leadscope postgres \
  -c "DROP DATABASE IF EXISTS leadscope;" \
  -c "CREATE DATABASE leadscope;"
docker compose exec -T postgres psql -U leadscope leadscope < db/schema.sql
echo "✅ Database reset complete."
