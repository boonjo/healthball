#!/usr/bin/env bash
# Wipe and re-seed the DB, then recompute all risk scores.
# Run from the backend/ directory with the venv active.
set -e

cd "$(dirname "$0")"

echo "=== Seeding squad + injuries ==="
python seed.py

echo ""
echo "=== Computing risk scores ==="
python model/train.py

echo ""
echo "Done. DB is up to date."
