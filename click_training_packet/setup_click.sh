#!/usr/bin/env bash
set -euo pipefail

# Run from Ubuntu/WSL. This script creates a NEW directory only.
kit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="${1:-$HOME/click-training}"
if [[ -e "$project_dir" ]]; then
    echo "Directory already exists: $project_dir" >&2
    echo "Choose a new path as the first argument; no files were changed." >&2
    exit 1
fi
git clone --depth 1 --branch 8.1.8 https://github.com/pallets/click.git "$project_dir"
cd -- "$project_dir"
git checkout --detach 934813e4d421071a1b3db3973c02fe2721359a6e
test "$(git rev-parse HEAD)" = 934813e4d421071a1b3db3973c02fe2721359a6e
rm -rf -- .git
cp -R -- "$kit_dir/opencode-setup/." .
python3 -m venv .venv
.venv/bin/python -m pip install -e . -r requirements/tests.txt
.venv/bin/python -m pytest -q tests
echo "Clean project ready at: $project_dir"
echo "Activate its .venv before starting OpenCode. This copy has no agent solution or checker feedback."
