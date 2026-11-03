#!/usr/bin/env bash
# Run lint + tests in the project venv.
set -euo pipefail
cd "$(dirname "$0")/.."
unset PYTHONPATH  # don't let a host PYTHONPATH shadow the venv's packages
source .venv/bin/activate
python scripts/gen_translations.py >/dev/null
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
python -m pytest -q -p no:cacheprovider --cov --cov-report=term-missing "$@"
