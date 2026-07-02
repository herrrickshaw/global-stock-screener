# vCRUD System - Quick Reference Cheatsheet

## Setup (First Time)

```bash
# 1. Install PostgreSQL
brew install postgresql@16
brew services start postgresql@16

# 2. Create database
psql postgres
CREATE DATABASE vcrud;
CREATE USER vcrud_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE vcrud TO vcrud_user;
\q

# 3. Install Python packages
pip install -r requirements_vcrud.txt

# 4. Set environment (optional)
export DATABASE_URL="postgresql://vcrud_user:password@localhost/vcrud"
```

## CLI Reference

### Shorthand
```bash
alias vcrud="python vcrud_cli.py --db postgresql://vcrud_user:password@localhost/vcrud --repo /path/to/repo"
```

### Create Operations (Index Files)

```bash
# Index single file
vcrud create --file myfile.py --branch main

# Index pattern of files
vcrud create --pattern "cache_seed/*.parquet" --branch main

# Batch index entire directory
vcrud batch-index --branch main

# Batch index with specific patterns
vcrud batch-index --branch main --patterns "*.py" "*.parquet" "*.csv"
```

### Read Operations (Retrieve Info)

```bash
# Get file metadata
vcrud read --file cache_seed/cleaned_long.parquet --branch main

# List all files on branch (top 50 by size)
vcrud list --branch main

# Get branch statistics
vcrud stats --branch main

# Get caching optimization hints
vcrud hints --branch main

# Get access patterns for top files
vcrud top-retrieval --branch main --limit 10
```

### Update Operations (Refresh Metadata)

```bash
# Update file after local changes
vcrud update --file myfile.py --branch main

# Update with Git commit reference
vcrud update --file myfile.py --branch main --commit abc123def456
```

### Delete Operations (Soft Delete)

```bash
# Soft delete file (preserves history)
vcrud delete --file deprecated.py --branch main

# Delete with commit reference
vcrud delete --file deprecated.py --branch main --commit abc123def456
```

### Analysis Operations

```bash
# Full branch scan and index
vcrud scan-branch --branch main

# Find duplicate files (all branches)
vcrud duplicates

# Compare two branches
vcrud compare --branch1 main --branch2 develop

# Get file version history
vcrud history --file myfile.py --branch main

# Storage optimization report
vcrud optimize --branch main

# Export branch summary (JSON)
vcrud export --branch main --output summary.json

# Export with custom threshold
vcrud export --branch main --output summary.json --ratio-threshold 0.90
```

## Python API Quick Ref

```python
from db_handler import DatabaseHandler, CompressionManager, GitBranchScanner
from vcrud_manager import VersionedCRUDManager

# Initialize
db = DatabaseHandler('postgresql://vcrud_user:pass@localhost/vcrud')
vcrud = VersionedCRUDManager(db, '/path/to/repo')

# Create
vcrud.create_file('path/file.py', 'main')
vcrud.create_many('main', ['file1.py', 'file2.py'])

# Read
record = vcrud.read_file('path/file.py', 'main')
files = db.list_files_by_branch('main')
stats = db.get_branch_stats('main')

# Update
vcrud.update_file('path/file.py', 'main')

# Delete
vcrud.delete_file('path/file.py', 'main')

# Analysis
vcrud.scan_branch_and_index('main')
vcrud.find_duplicates_across_branches()
vcrud.compare_branches('main', 'develop')
vcrud.get_file_history('path/file.py', 'main')
vcrud.optimize_storage('main')
```

## Common Patterns

### Index Everything and Analyze

```bash
# Full workflow
vcrud scan-branch --branch main         # Index all files
vcrud stats --branch main               # Check size stats
vcrud duplicates                        # Find wasted space
vcrud optimize --branch main            # Get recommendations
vcrud export --branch main --output report.json  # Export
```

### Compare Branches Before Merge

```bash
vcrud scan-branch --branch develop
vcrud compare --branch1 main --branch2 develop

# What will be added/removed
```

### Find Large Files

```bash
vcrud list --branch main | sort -k2 -rn | head -20

# Or use Python
files = db.list_files_by_branch('main')
large = sorted(files, key=lambda f: f.size_bytes, reverse=True)[:20]
```

### Check Compression Effectiveness

```bash
# Via CLI
vcrud stats --branch main
# Look at: total_size_mb, compressed_size_mb, avg_compression_ratio

# Via Python
stats = db.get_branch_stats('main')
print(f"Saved: {stats['bytes_saved_mb']:.1f} MB")
print(f"Ratio: {stats['avg_compression_ratio']:.1%}")
```

### Track File Changes

```bash
# Get history
vcrud history --file myfile.py --branch main

# Via Python
history = db.get_file_history('myfile.py', 'main')
for v in history:
    print(f"{v['operation']}: {v['git_commit'][:8]} - {v['size_bytes']} bytes")
```

### Get Top Files for Caching

```bash
# Via CLI
vcrud hints --branch main

# Via Python
files = db.get_top_retrieval_files('main', limit=10)
for f in files:
    print(f"{f['file_path']}: {f['retrieval_count']} accesses")
```

## Database Queries (SQL)

```sql
-- Connect
psql -U vcrud_user -d vcrud

-- Total files by branch
SELECT b.branch_name, COUNT(*) as files 
FROM files f 
JOIN branches b ON f.branch_id = b.id 
GROUP BY b.branch_name 
ORDER BY files DESC;

-- Total size by branch
SELECT b.branch_name, 
       SUM(f.size_bytes)/1024/1024 as size_mb,
       SUM(f.compressed_size)/1024/1024 as compressed_mb
FROM files f 
JOIN branches b ON f.branch_id = b.id 
GROUP BY b.branch_name 
ORDER BY size_mb DESC;

-- Top 10 accessed files
SELECT file_path, retrieval_count, size_bytes/1024/1024 as size_mb
FROM files
WHERE branch_id = (SELECT id FROM branches WHERE branch_name = 'main')
ORDER BY retrieval_count DESC LIMIT 10;

-- Duplicates (files appearing multiple times)
SELECT checksum, COUNT(*) as copies, SUM(size_bytes)/1024/1024 as wasted_mb
FROM files
GROUP BY checksum
HAVING COUNT(*) > 1
ORDER BY wasted_mb DESC;

-- Poor compression candidates (> 85%)
SELECT file_path, compression_ratio, size_bytes/1024/1024 as size_mb
FROM files
WHERE compression_ratio > 0.85
ORDER BY size_bytes DESC;

-- All versions of a file
SELECT fv.*, f.file_path
FROM file_versions fv
JOIN files f ON fv.file_id = f.id
WHERE f.file_path = 'myfile.py'
ORDER BY fv.changed_at DESC;
```

## Troubleshooting

```bash
# Test DB connection
psql -U vcrud_user -d vcrud -h localhost -c "SELECT 1;"

# Check tables exist
psql -U vcrud_user -d vcrud -c "\dt"

# Look at schema
psql -U vcrud_user -d vcrud -c "\d files"

# View file count
psql -U vcrud_user -d vcrud -c "SELECT COUNT(*) FROM files;"

# Find large queries (slow)
psql -U vcrud_user -d vcrud -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

## Performance Tips

```python
# For 10,000+ files, use batch indexing
batch_size = 500
for i in range(0, len(records), batch_size):
    for record in records[i:i+batch_size]:
        db.create_file(record)
    db.conn.commit()  # Commit per batch, not per file

# Skip compression for already-compressed formats
skip_patterns = ['*.zip', '*.gz', '*.jpg', '*.mp4']

# Use connection pooling for concurrent operations
# (Not implemented in basic version, but recommended for production)
```

## Common Workflows for Stock Market Project

### Setup for Your Repo

```bash
# Navigate to your project
cd /Users/umashankar/Downloads/code/python_files

# Create alias
alias vcrud="python vcrud_cli.py --db postgresql://vcrud_user:password@localhost/vcrud --repo ."

# Index main branch
vcrud scan-branch --branch main

# Quick check
vcrud stats --branch main
```

### Compare Feature Branches

```bash
# After creating feature branch
vcrud scan-branch --branch feature-darvas

# See differences
vcrud compare --branch1 main --branch2 feature-darvas

# Check file sizes
vcrud stats --branch feature-darvas
```

### Before Committing Large Files

```bash
# Check if file already exists
vcrud duplicates | grep -i myfile

# If it's a data file > 100MB
vcrud optimize --branch main | grep "poor_compression"

# Consider: Add to .gitignore or use Git LFS
```

### Daily Development Workflow

```bash
# Morning: Check what's most accessed
vcrud hints --main

# Download these for faster local testing:
# - cache_seed/cleaned_long.parquet
# - market_data_cache.parquet
# - backtest_data.csv

# Evening: Export summary
vcrud export --branch main --output daily_report.json
```

## Comparison Cheatsheet

| Task | CLI | Python |
|------|-----|--------|
| Index files | `vcrud scan-branch` | `vcrud.scan_branch_and_index()` |
| Get stats | `vcrud stats --branch main` | `db.get_branch_stats('main')` |
| Find dupes | `vcrud duplicates` | `vcrud.find_duplicates_across_branches()` |
| Compare | `vcrud compare --branch1 main --branch2 dev` | `vcrud.compare_branches('main', 'dev')` |
| History | `vcrud history --file f.py --branch main` | `db.get_file_history('f.py', 'main')` |
| Optimize | `vcrud optimize --branch main` | `vcrud.optimize_storage('main')` |
| Export | `vcrud export --branch main -o out.json` | `vcrud.export_summary('main')` |

---

**Pro Tip:** Create shell functions for frequently used commands:

```bash
# Add to ~/.zshrc
vcrud_main() { python vcrud_cli.py --db postgresql://vcrud_user:password@localhost/vcrud --repo /Users/umashankar/Downloads/code/python_files $@ }

# Then use:
vcrud_main stats --branch main
vcrud_main duplicates
```
