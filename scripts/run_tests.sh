#!/bin/bash
set -e

echo "=== Building & Running Stages Service Test Suite ==="
STAGES_TEST_IMG=$(docker build -q -f services/stages/Dockerfile.test ./services/stages)
docker run --rm --network jenex_ai_default $STAGES_TEST_IMG

echo "=== Building & Running Evaluator Service Test Suite ==="
EVAL_TEST_IMG=$(docker build -q -f services/evaluator/Dockerfile.test ./services/evaluator)
docker run --rm --network jenex_ai_default $EVAL_TEST_IMG

echo "=== All Test Suites Completed Successfully ==="
