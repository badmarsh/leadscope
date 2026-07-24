#!/usr/bin/env bash
set -e


echo "=== Running Stages Unit Tests (Docker) ==="
docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "\
  pip install --quiet -r services/stages/requirements-dev.txt && \
  PYTHONPATH=/app/services/stages pytest services/stages/tests -v --tb=short"

echo "=== Running Evaluator Unit Tests (Docker) ==="
docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "\
  pip install --quiet -r services/evaluator/requirements.txt pytest pytest-mock && \
  PYTHONPATH=/app/services/evaluator pytest services/evaluator/tests -v --tb=short"

echo "=== Running Integration Tests (Docker) ==="
docker run --rm -v "$(pwd):/app" -w /app --network jenex_ai_default \
  -e EVALUATOR_URL=http://evaluator:8001 \
  -e STAGES_URL=http://stages:8002 \
  -e DASHBOARD_URL=http://dashboard:3000 \
  python:3.12-slim bash -c "\
    pip install --quiet requests pytest && \
    pytest tests/integration -v --tb=short"

echo "=== All Tests Passed ==="
