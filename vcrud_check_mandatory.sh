#!/bin/bash
# Mandatory check before merge to main
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Mandatory vCRUD check on $BRANCH..."
python3 find_duplicates_standalone.py && echo "✓ Check passed" || exit 1
