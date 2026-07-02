#!/bin/bash
# vCRUD Mandatory Workflow - Run before commit/push
echo "Running vCRUD mandatory workflow..."
python3 find_duplicates_standalone.py
mkdir -p vcrud_reports
echo "✓ vCRUD check complete - reports saved to vcrud_reports/"
