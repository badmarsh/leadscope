# conftest.py — repo root
# HARDENING: This file intentionally does NOT add service directories to
# sys.path. Each service must be tested in isolation:
#   python -m pytest services/stages
#   python -m pytest services/evaluator
# Running `pytest` from the repo root only collects non-service tests
# (e.g. integration tests in /tests/).
import sys
import os

# Explicitly REMOVE any service directory from sys.path to prevent
# namespace collisions between services/stages/config.py and
# services/evaluator/config.py.
_repo_root = os.path.dirname(__file__)
for _service_dir in ["services/stages", "services/evaluator", "services/crawler"]:
    _abs = os.path.join(_repo_root, _service_dir)
    if _abs in sys.path:
        sys.path.remove(_abs)
