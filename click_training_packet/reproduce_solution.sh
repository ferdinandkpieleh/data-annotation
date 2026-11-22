#!/usr/bin/env bash
set -euo pipefail

# Reproduce the SAVED solution attempt, not a new model run.
kit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="${1:-$HOME/click-solution-review}"
bash "$kit_dir/setup_click.sh" "$project_dir"
cd -- "$project_dir"
patch -p1 < "$kit_dir/evidence/celery_solution.patch"
cp -R -- "$kit_dir/da_training_project_tests" .
echo "Running the saved solution against the reviewed verifiers. An assertion failure is expected."
.venv/bin/python -m pytest -q tests da_training_project_tests --tb=short
