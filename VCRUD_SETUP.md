# vCRUD System: Git-Backed File Tracking Setup Guide

A comprehensive system for tracking files across Git branches, optimizing retrieval, and managing data compression. Uses PostgreSQL for central tracking and gzip for balanced compression.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     vCRUD File System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PostgreSQL Database                                           │
│  ├── branches: Track branch metadata                           │
│  ├── files: File records with compression data                 │
│  ├── file_versions: Git-backed version history                │
│  ├── file_dedup: Cross-branch deduplication                    │
│  ├── retrieval_cache: Access optimization                      │
│  └── compression_stats: Optimization analytics                 │
│                                                                 │
│  Local File System                                             │
│  ├── Repository files (tracked by Git)                         │
│  └── Indexed by GitBranchScanner                              │
│                                                                 │
│  vCRUD Manager (C/R/U/D Operations)                           │
│  ├── CREATE: Index files with compression                      │
│  ├── READ: Track access, suggest caching                       │
│  ├── UPDATE: Refresh metadata after changes                    │
│  └── DELETE: Soft delete with history                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### 1. Install PostgreSQL

**macOS (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16

# Verify installation
psql --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Download installer from https://www.postgresql.org/download/windows/

### 2. Create Database

```bash
# Connect to PostgreSQL
psql postgres

# Inside psql:
CREATE DATABASE vcrud;
CREATE USER vcrud_user WITH PASSWORD 'your_secure_password';
ALTER ROLE vcrud_user SET client_encoding TO 'utf8';
ALTER ROLE vcrud_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE vcrud_user SET default_transaction_deferrable TO on;
GRANT ALL PRIVILEGES ON DATABASE vcrud TO vcrud_user;
\q
```

### 3. Install Python Dependencies

```bash
cd /path/to/your/project

pip install psycopg2-binary gzip pathlib
# Or with requirements.txt:
pip install -r requirements_vcrud.txt
```

**requirements_vcrud.txt:**
```
psycopg2-binary>=2.9.0
```

### 4. Configure Connection

Create `.env` or modify your config:

```bash
# .env
DATABASE_URL=postgresql://vcrud_user:your_secure_password@localhost:5432/vcrud
REPO_PATH=/path/to/your/repository
```

## Quick Start

### Example 1: Index Your Current Branch

```bash
# Scan main branch and index all files
python vcrud_cli.py scan-branch --branch main \
  --db postgresql://vcrud_user:password@localhost/vcrud \
  --repo /path/to/repo

# Output:
# Branch Scan Complete
# Branch:           main
# Files Indexed:    2,681
# Total Size:       45.3 MB
# Compressed Size:  18.7 MB
# Avg Ratio:        41.3%
```

### Example 2: Add Individual File

```bash
python vcrud_cli.py create \
  --file custom_screener.py \
  --branch main \
  --db postgresql://vcrud_user:password@localhost/vcrud
```

### Example 3: Get Retrieval Optimization Hints

```bash
python vcrud_cli.py hints --branch main

# Output:
# Retrieval Optimization Hints
# ==================================================
# Branch: main
#
# Statistics:
#   total_files: 147
#   total_size_mb: 234.5
#   compressed_size_mb: 98.2
#   avg_compression_ratio: 41.9%
#
# Top Files to Cache:
#   1. cache_seed/cleaned_long.parquet - 125.3 MB, 42 accesses
#   2. market_data_cache.parquet - 78.2 MB, 38 accesses
#   3. backtest_data.csv - 45.1 MB, 31 accesses
#
# Recommendation: Pre-cache 'cache_seed/cleaned_long.parquet' (125.3 MB,
# 42.0% of traffic). Total 147 files, 234.5 MB, 41.9% avg compression.
```

### Example 4: Find Duplicate Files Across Branches

```bash
python vcrud_cli.py duplicates

# Output:
# Duplicate Files Found
# ==================================================
# Total unique files with duplicates: 23
#
# Checksum:  a1b2c3d4...
#   Copies:    3
#   Wasted:    156.7 MB
#   Branches:  main, develop, feature-auth
#   Files:     Downloads/cache_seed/cleaned_long.parquet...
```

### Example 5: Compare Two Branches

```bash
python vcrud_cli.py compare --branch1 main --branch2 develop

# Output:
# Branch Comparison
# ==================================================
# main vs develop
#
# Only in main (12 files):
#   - old_config.py
#   - deprecated_utils.py
#   ...
#
# Only in develop (8 files):
#   - new_feature.py
#   - experimental_module.py
#   ...
#
# Common files: 135
```

### Example 6: Storage Optimization Report

```bash
python vcrud_cli.py optimize --branch main

# Output:
# Storage Optimization Report
# ==================================================
# Branch: main
# Threshold: 85% compression ratio
#
# Potential savings: 287.4 MB
#   From poor compression: 15 files
#   From duplicate files: 23 groups
#   Total duplicate waste: 156.7 MB
#
# Files with poor compression:
#   large_binary.bin                    2,048.5 MB (89%)
#   cache.db                            1,024.3 MB (87%)
```

### Example 7: Export Summary for Analysis

```bash
python vcrud_cli.py export --branch main --output branch_report.json

# Creates branch_report.json with:
# {
#   "branch": "main",
#   "timestamp": "2026-07-02T...",
#   "statistics": { ... },
#   "total_files": 147,
#   "top_accessed_files": [ ... ],
#   "all_files": [ ... ]
# }
```

## Use Cases

### Scenario 1: Your Stock Market Project

You have multiple branches for different features. Track file changes:

```bash
# Index all branches
for branch in main develop feature-darvas feature-ml; do
  python vcrud_cli.py scan-branch --branch $branch
done

# Find which files consume most space
python vcrud_cli.py stats --branch main

# Identify files used by main but not develop
python vcrud_cli.py compare --branch1 main --branch2 develop

# Get caching strategy for fastest local development
python vcrud_cli.py hints --branch main
```

### Scenario 2: Data Compression Optimization

Identify opportunities to reduce storage:

```bash
# Find all duplicate cache files
python vcrud_cli.py duplicates

# Find files that don't compress well (maybe should move to LFS)
python vcrud_cli.py optimize --branch main --ratio-threshold 0.90
```

### Scenario 3: File History & Auditing

Track how a specific file evolved:

```bash
python vcrud_cli.py history \
  --file cache_seed/cleaned_long.parquet \
  --branch main

# Shows:
# - When file was created
# - All updates with size changes
# - Commits that modified it
# - Whether it was deleted/restored
```

### Scenario 4: Sync Strategy for GitHub

Determine what to clone and what to fetch on-demand:

```python
# Get branch stats
stats = vcrud.db.get_branch_stats('main')

# Large files that are frequently accessed
top_files = vcrud.db.get_top_retrieval_files('main', limit=10)

# Decision: Clone these 10 files locally, fetch others on-demand
for f in top_files:
    print(f"Pre-fetch: {f['file_path']} ({f['size_bytes']/1024**2:.1f} MB)")
```

## API Reference

### DatabaseHandler

```python
from db_handler import DatabaseHandler, FileRecord

# Initialize
db = DatabaseHandler('postgresql://user:pass@localhost/vcrud')

# CRUD operations
file_id = db.create_file(record)          # CREATE
record = db.read_file(path, branch)       # READ
db.update_file(record)                     # UPDATE
db.delete_file(path, branch)               # DELETE

# Analysis
stats = db.get_branch_stats(branch)       # Stats
dupes = db.find_duplicates()              # Find duplicates
history = db.get_file_history(path, branch)  # Version history
top = db.get_top_retrieval_files(branch)  # Access patterns
```

### VersionedCRUDManager

```python
from vcrud_manager import VersionedCRUDManager

vcrud = VersionedCRUDManager(db, '/path/to/repo')

# High-level operations
vcrud.create_file(path, branch)           # Add to tracking
vcrud.read_file(path, branch)             # Get with tracking
vcrud.update_file(path, branch)           # Refresh after changes
vcrud.delete_file(path, branch)           # Soft delete

# Analysis
vcrud.scan_branch_and_index(branch)       # Full branch scan
vcrud.find_duplicates_across_branches()   # Dedup report
vcrud.compare_branches(b1, b2)            # Diff branches
vcrud.optimize_storage(branch)            # Optimization hints
vcrud.export_summary(branch)              # JSON export
```

### CompressionManager

```python
from db_handler import CompressionManager

# Compress file
compressed, ratio = CompressionManager.compress_file(path)

# Decompress
original = CompressionManager.decompress_file(compressed)

# Checksums
sha256 = CompressionManager.compute_checksum(path)
```

## Performance Tuning

### Database Indexing

Indexes are created automatically, but you can add more:

```sql
-- For large deployments
CREATE INDEX idx_files_size ON files(size_bytes);
CREATE INDEX idx_files_checksum_branch ON files(checksum, branch_id);
CREATE INDEX idx_retrieval_accessed ON retrieval_cache(last_accessed);
```

### Compression Strategy

Adjust compression level (1-9, default 6):

```python
# In CompressionManager.compress_file():
compressed = gzip.compress(original_data, compresslevel=9)  # Slower, better ratio
compressed = gzip.compress(original_data, compresslevel=1)  # Faster, worse ratio
```

### Batch Operations

For indexing large repos (10,000+ files):

```python
# Process in chunks to avoid memory issues
batch_size = 500
for i in range(0, len(records), batch_size):
    batch = records[i:i+batch_size]
    for record in batch:
        db.create_file(record)
    db.conn.commit()  # Commit per batch
```

## Troubleshooting

### Connection Errors

```bash
# Test PostgreSQL connection
psql -U vcrud_user -d vcrud -h localhost

# Check PostgreSQL logs
# macOS: ~/Library/Logs/Homebrew/postgresql*
# Linux: /var/log/postgresql/
```

### Out of Memory During Compression

```python
# Skip files larger than 100MB
if file.size_bytes > 100 * 1024 * 1024:
    record.compressed_size = None  # Skip compression
    record.compression_ratio = None
```

### Disk Space Issues

```bash
# Check compressed vs original sizes
psql -d vcrud -c "
  SELECT 
    SUM(size_bytes) as original,
    SUM(compressed_size) as compressed,
    ROUND(100 * (1 - SUM(compressed_size)::float / SUM(size_bytes)), 1) as percent_saved
  FROM files;
"
```

## Advanced Features

### Git-Backed Versioning

Every file change is tied to Git commits:

```python
# Get all versions of a file from Git history
history = vcrud.get_file_history('myfile.py', 'main')

for version in history:
    print(f"{version['operation']} - {version['git_commit'][:8]} - {version['changed_at']}")
    print(f"  Size: {version['size_bytes']} → {version['compressed_size']}")
```

### Cross-Branch Deduplication

Automatically detect and report wasted space:

```python
# Find files identical across branches
dupes = db.find_duplicates()

for dup in dupes:
    if dup['duplicate_count'] > 2:
        print(f"File appears {dup['duplicate_count']} times")
        print(f"Wasting {dup['total_wasted'] / 1024**2:.1f} MB")
        print(f"Appears in: {', '.join(dup['branches'])}")
```

### Retrieval Optimization

Use access patterns for smart caching:

```python
hints = vcrud.read_with_retrieval_hints('main')

# Top 10 files account for ~80% of access
for f in hints['top_retrieval_candidates'][:10]:
    # Pre-download these files in CI/CD pipelines
    # Use local cache in development
    pass
```

## Integration Examples

### With Your Stock Market Project

```python
from vcrud_manager import VersionedCRUDManager
from db_handler import DatabaseHandler

db = DatabaseHandler('postgresql://vcrud_user:pass@localhost/vcrud')
vcrud = VersionedCRUDManager(db, '/Users/umashankar/Downloads/code/python_files')

# Track your screening pipeline
for branch in ['main', 'feature-darvas', 'feature-ml']:
    vcrud.scan_branch_and_index(branch)

# Identify which branch uses most cache data
for branch in ['main', 'feature-darvas']:
    stats = db.get_branch_stats(branch)
    print(f"{branch}: {stats['total_size_mb']:.1f} MB")
```

### With CI/CD Pipeline

```bash
#!/bin/bash
# Pre-job: Download only top 10 most-used files
python vcrud_cli.py hints --branch main | grep "Pre-cache" | while read line; do
    FILE=$(echo "$line" | awk '{print $2}')
    git lfs pull --include "$FILE"  # Using Git LFS for large files
done
```

### With Data Pipeline

```python
# Track which data files are used by each screening pipeline
pipeline_branches = {
    'darvas_screening': 'feature-darvas',
    'ml_screening': 'feature-ml',
    'value_screening': 'main'
}

for pipeline, branch in pipeline_branches.items():
    files = vcrud.db.list_files_by_branch(branch)
    data_files = [f for f in files if 'cache_seed' in f.path or '.parquet' in f.path]
    print(f"{pipeline}: {sum(f.size_bytes for f in data_files) / 1024**2:.1f} MB")
```

## Next Steps

1. **Setup PostgreSQL** - Run the installation commands
2. **Configure Connection** - Set DATABASE_URL
3. **Index Your Repo** - Run `vcrud_cli.py scan-branch --branch main`
4. **Explore** - Try comparison, duplication, and optimization commands
5. **Integrate** - Add vCRUD calls to your CI/CD pipelines

## Support

For issues or enhancements, check:
- Database logs: `psql -d vcrud -c "SELECT * FROM files LIMIT 5;"`
- Git integration: Ensure repository is a valid Git repo
- Compression: Check file types that don't compress well
