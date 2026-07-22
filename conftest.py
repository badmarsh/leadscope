import os
import sys

# Add repo root to sys.path so services can be imported as services.evaluator or services.stages
ROOT_DIR = os.path.dirname(__file__)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
