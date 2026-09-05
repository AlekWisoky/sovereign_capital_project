import os
import sys


# Ensure `import victor_ai_bot` works when running tests from repo root.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Preserve the suite's existing top-level test-module imports (for example
# `from test_capital_demand_contract import ...`) when pytest collects from
# the backend test directory.
TESTS = os.path.abspath(os.path.dirname(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)
