#!/usr/bin/env bash
# Wipe and re-seed the DB, then recompute all risk scores.
# Run from the backend/ directory with the venv active.
set -e

cd "$(dirname "$0")"

echo "=== Seeding squad + injuries ==="
if ! python seed.py; then
  echo "ERROR: seed.py failed — DB may be in a partially wiped state. Fix the error and re-run."
  exit 1
fi

echo ""
echo "=== Fetching live minutes (Understat) ==="
echo "    If this fails, seed.py estimates remain and the pipeline continues."
echo "    To load from a manual FBref CSV: python etl/fetch_minutes.py --csv <path>"
python etl/fetch_minutes.py

echo ""
echo "=== Computing risk scores ==="
if ! python model/train.py; then
  echo "ERROR: train.py failed — risk_scores table is empty. Fix the error and re-run."
  exit 1
fi

echo ""
echo "Done. DB is up to date."
