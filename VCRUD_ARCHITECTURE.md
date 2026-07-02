# vCRUD System - Complete Architecture & Design

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          vCRUD File Management System                       │
│                    (Git-Backed Versioning + PostgreSQL)                     │
└─────────────────────────────────────────────────────────────────────────────┘

                             ┌─────────────────┐
                             │   User/CLI      │
                             │  (vcrud_cli.py) │
                             └────────┬────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
           ┌────────▼────────┐              ┌──────────▼──────────┐
           │  vCRUD Manager  │              │   Database Handler  │
           │ (vcrud_manager) │              │   (db_handler)      │
           └────────┬────────┘              └──────────┬──────────┘
                    │                                   │
         ┌──────────┼──────────┐              ┌────────┴────────┐
         │          │          │              │                 │
    ┌────▼──┐  ┌────▼──┐  ┌───▼──┐      ┌───▼──┐          ┌───▼──┐
    │ Idx   │  │ Git   │  │Comp  │      │SQL   │          │SQL   │
    │Local  │  │Branch │  │Mgr   │      │CRUD  │          │Anal  │
    │Files  │  │Scanner│  │      │      │      │          │ysis  │
    └───────┘  └───────┘  └──────┘      └──────┘          └──────┘
         │          │          │              │                 │
         └──────────┼──────────┴──────────────┼─────────────────┘
                    │                        │
         ┌──────────▼────────────────────────▼────────┐
         │        PostgreSQL Database                  │
         │  ┌─────────────────────────────────────┐  │
         │  │ Tables:                             │  │
         │  │  - branches (metadata)              │  │
         │  │  - files (file records)             │  │
         │  │  - file_versions (Git history)     │  │
         │  │  - file_dedup (duplicates)         │  │
         │  │  - retrieval_cache (optimization)  │  │
         │  │  - compression_stats (analytics)   │  │
         │  └─────────────────────────────────────┘  │
         │                                            │
         └────────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
   ┌────▼──────┐              ┌────────▼────┐
   │Git Repo   │              │Local Files  │
   │ .git/     │              │Filesystem   │
   │ commits   │              │             │
   └───────────┘              └─────────────┘
```

## Data Flow: The vCRUD Cycle

### 1. CREATE: Index a File

```
User Request (CLI/API)
        │
        ▼
vcrud.create_file('myfile.py', 'main')
        │
        ├─► Check file exists
        │
        ├─► Compute SHA256 checksum
        │
        ├─► Compress with gzip (ratio %)
        │
        ├─► Get Git commit (git log -1)
        │
        ▼
Create FileRecord
        │
        ▼
db.create_file(record)
        │
        ├─► INSERT into files table
        │
        ├─► INSERT into file_versions (CREATE op)
        │
        ▼
Return file_id
        │
        ▼
Logged to database ✓
```

### 2. READ: Retrieve File Info

```
User Request: vcrud.read_file('myfile.py', 'main')
        │
        ▼
SELECT from files WHERE path='myfile.py' AND branch_id=X
        │
        ▼
Increment retrieval_count
        │
        ▼
Update retrieval_cache for optimization
        │
        ▼
Return FileRecord
        │
        ├─► path
        ├─► size_bytes
        ├─► checksum
        ├─► compression_ratio
        ├─► retrieval_count
        └─► git_commit
```

### 3. UPDATE: Refresh After Changes

```
User edits file locally
        │
        ▼
vcrud.update_file('myfile.py', 'main')
        │
        ├─► Re-compute checksum
        ├─► Re-compress
        ├─► Get new Git commit
        │
        ▼
UPDATE files table (size, checksum, ratio)
        │
        ▼
INSERT into file_versions (UPDATE op)
        │
        ▼
Version history preserved ✓
```

### 4. DELETE: Soft Delete with History

```
vcrud.delete_file('oldfile.py', 'main')
        │
        ├─► INSERT into file_versions (DELETE op)
        │   - Records what was deleted
        │   - Preserves commit reference
        │
        ▼
DELETE from files (soft delete)
        │
        ▼
History still intact in file_versions ✓
Can restore if needed
```

## Database Schema Deep Dive

### Tables & Relationships

```sql
┌─────────────────────────────────────────────────────────────────┐
│ branches                                                        │
├─────────┬──────────────┬──────────────────────────────────────┤
│ id (PK) │ branch_name  │ last_scanned, total_files, metadata  │
└────┬────┴──────────────┴──────────────────────────────────────┘
     │
     │ 1:N relationship
     │
┌────▼─────────────────────────────────────────────────────────────────┐
│ files                                                               │
├──────────┬─────────────┬──────────┬─────────────────────────────────┤
│ id (PK)  │ file_path   │ size     │ checksum, compressed_size,     │
│ branch_id│ git_commit  │ checksum │ compression_ratio, retrieval_ct│
└────┬─────┴─────────────┴──────────┴─────────────────────────────────┘
     │
     │ 1:N relationship
     │
┌────▼──────────────────────────────────────────────────────────────┐
│ file_versions                                                    │
├────────────┬─────────┬──────────────────────────────────────────┤
│ id (PK)    │ git_com │ size, compressed, changed_at, operation │
│ file_id(FK)│ mit     │ (CREATE, UPDATE, DELETE)               │
└────────────┴─────────┴──────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ file_dedup                                                     │
├──────────┬────────────────────────────────────────────────────┤
│ checksum │ duplicate_count, total_wasted_bytes,               │
│ (UNIQUE) │ branches_list (JSONB), primary_file_id             │
└──────────┴────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│ retrieval_cache                                               │
├──────────────┬──────────────────────────────────────────────┤
│ file_id (FK) │ access_count, last_accessed, cache_priority  │
│ branch_id    │                                              │
└──────────────┴──────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ compression_stats                                              │
├─────────────┬─────────────────────────────────────────────────┤
│ branch_id   │ total_original_bytes, total_compressed_bytes,   │
│ (FK)        │ overall_ratio, best_ratio, worst_ratio          │
└─────────────┴─────────────────────────────────────────────────┘
```

### Key Design Decisions

**Git-Backed Versioning:**
- `file_versions` table stores references to git commits, NOT full copies
- Minimal storage overhead while keeping full history
- Can reconstruct file state at any commit

**Deduplication Strategy:**
- Separate `file_dedup` table for efficient duplicate detection
- Tracks which branches have identical files
- Enables storage optimization recommendations

**Retrieval Tracking:**
- `retrieval_cache` monitors access patterns
- Enables data locality optimization
- Helps decide what to pre-fetch in CI/CD

**Compression Metadata:**
- Ratio tracked per-file (not global)
- Enables identification of poorly-compressing files
- Supports optimization recommendations

## File Record Data Class

```python
@dataclass
class FileRecord:
    # Core identification
    path: str                    # Relative path in repo
    branch: str                  # Branch name
    
    # Size & compression
    size_bytes: int              # Original file size
    compressed_size: int         # After gzip compression
    compression_ratio: float     # Compressed/Original %
    
    # Integrity
    checksum: str               # SHA256 hash
    
    # Versioning
    git_commit: str             # Last commit that touched file
    last_modified: datetime     # File mtime
    
    # Analytics
    retrieval_count: int        # How many times read
```

## vCRUD Manager Architecture

### Three Layers

```
┌─────────────────────────────────────────┐
│ Layer 1: User Interface                 │
│ - CLI (vcrud_cli.py)                    │
│ - Python API (high-level)               │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│ Layer 2: vCRUD Manager                  │
│ - VersionedCRUDManager                  │
│ - LocalFileIndexer                      │
│ - Convenience methods                   │
│ - Analysis & optimization               │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│ Layer 3: Database & Compression         │
│ - DatabaseHandler                       │
│ - CompressionManager                    │
│ - GitBranchScanner                      │
└─────────────────────────────────────────┘
```

### vCRUD Operations

```python
# CREATE: Add new files
vcrud.create_file(path, branch)          # Single file
vcrud.create_many(branch, paths)         # Batch

# READ: Retrieve metadata
vcrud.read_file(path, branch)            # Single file
vcrud.read_with_retrieval_hints(branch)  # Optimization tips

# UPDATE: Refresh after changes
vcrud.update_file(path, branch)          # Single file

# DELETE: Soft delete
vcrud.delete_file(path, branch)          # Preserves history

# ANALYSIS
vcrud.scan_branch_and_index(branch)      # Full indexing
vcrud.find_duplicates_across_branches()  # Dedup report
vcrud.compare_branches(b1, b2)           # Branch diff
vcrud.optimize_storage(branch)           # Recommendations
vcrud.export_summary(branch)             # JSON export
```

## Compression Strategy

### Algorithm: gzip (Deflate)

```
Original File
    │
    ├─► Read in 4KB chunks
    │
    ├─► Apply LZ77 (sliding window)
    │   - Find repeated sequences
    │   - Replace with references
    │
    ├─► Apply Huffman coding
    │   - Encode frequent bytes with fewer bits
    │   - Encode rare bytes with more bits
    │
    ├─► Add gzip header & checksum
    │
    ▼
Compressed File

Typical Results:
  - Text files (Python, CSV): 20-30% of original
  - JSON/YAML: 25-35% of original
  - Parquet/HDF5: 50-70% (already compressed)
  - Binary (images, video): 95-105% (incompressible)
```

### Compression Level Strategy

```
Level 1 (fastest):
  └─► Time: 1ms/MB  │  Ratio: 65-70%

Level 6 (default):
  └─► Time: 5ms/MB  │  Ratio: 40-50%  ← USED IN vCRUD

Level 9 (slowest):
  └─► Time: 20ms/MB │  Ratio: 38-42%
```

**Decision:** Level 6 chosen for balance between speed (indexing) and ratio (storage).

## Query Performance Analysis

### Fast Queries (< 50ms)

```sql
-- Single file lookup
SELECT * FROM files WHERE file_path = ? AND branch_id = ?;
└─► Index: (file_path, branch_id)

-- Top accessed files
SELECT * FROM files WHERE branch_id = ? ORDER BY retrieval_count DESC LIMIT 10;
└─► Indexed column: retrieval_count

-- Files by checksum
SELECT * FROM files WHERE checksum = ?;
└─► Index: checksum
```

### Moderate Queries (50-500ms)

```sql
-- All files on branch
SELECT * FROM files WHERE branch_id = ? ORDER BY file_path;
└─► Table scan + sort (147 files = ~100ms)

-- Duplicate detection
SELECT checksum, COUNT(*) FROM files GROUP BY checksum HAVING COUNT(*) > 1;
└─► Group by + aggregation (~200ms for 147 files)

-- Cross-branch comparison
SELECT file_path FROM files WHERE branch_id = ?
EXCEPT
SELECT file_path FROM files WHERE branch_id = ?;
└─► Set difference (~150ms per comparison)
```

### Slow Queries (>1000ms)

```sql
-- File history across all commits
SELECT * FROM file_versions ORDER BY changed_at DESC;
└─► Can have 10,000s+ versions, needs pagination

-- Optimization report
SELECT *, (1 - compressed_size::float/size_bytes) 
FROM files WHERE compression_ratio > 0.85;
└─► Complex calculation, large result set
```

**Mitigation:** Use LIMIT, add indexes, run during off-peak hours.

## Integration Points

### With Git Workflow

```
Developer pushes commit
        │
        ▼
Git hook (optional)
        │
        ├─► Call vcrud update --file <changed_file>
        │
        ├─► Updates database with new checksum
        │
        ├─► Logs to file_versions
        │
        ▼
CI/CD pipeline
        │
        ├─► Calls vcrud hints --branch $BRANCH
        │
        ├─► Gets top 5 files to download
        │
        ├─► Skips downloading others
        │
        ▼
Fast CI/CD execution
```

### With Data Pipelines

```
Stock market screening pipeline
        │
        ├─► Needs: nse_data_fetcher.py (updated daily)
        ├─► Needs: cache_seed/cleaned_long.parquet (125MB)
        ├─► Needs: market_calendar.py (rarely changes)
        │
        ▼
Query vCRUD: "Which are most accessed?"
        │
        ├─► cleaned_long.parquet: 42 accesses
        ├─► nse_data_fetcher.py: 38 accesses
        ├─► market_calendar.py: 2 accesses
        │
        ▼
Download strategy:
        ├─► Pre-fetch: cleaned_long.parquet (frequent)
        ├─► Pre-fetch: nse_data_fetcher.py (frequent)
        └─► Lazy-load: market_calendar.py (rare)
```

### With Storage Optimization

```
Over time, duplicate files accumulate:
  - cache_seed/cleaned_long.parquet on main (125MB)
  - cache_seed/cleaned_long.parquet on develop (125MB)
  - cache_seed/cleaned_long.parquet on feature-auth (125MB)
        │
        ▼
vcrud duplicates shows: 375MB wasted
        │
        ▼
Recommendations:
  1. Use Git LFS for large parquet files
  2. Add .gitattributes entry
  3. Clean up old copies
        │
        ▼
Save 375MB of repository size
```

## Scalability Considerations

### Current Implementation

| Metric | Capacity | Notes |
|--------|----------|-------|
| Files per branch | 10,000+ | No hard limit |
| Total database size | 500GB+ | PostgreSQL can handle |
| Query response | < 100ms | With proper indexing |
| Indexing speed | 100 files/sec | Includes compression |

### Bottlenecks & Solutions

**Bottleneck 1: Compression (CPU)**
```
Solution: Skip compression for files > 100MB
         or use streaming compression
```

**Bottleneck 2: Checksum computation (I/O)**
```
Solution: Cache checksums for unchanged files
         use stat() to detect changes
```

**Bottleneck 3: Database writes (Transaction overhead)**
```
Solution: Batch commits per 500 files
         use PostgreSQL COPY for bulk insert
```

**Bottleneck 4: Duplicate detection (Memory)**
```
Solution: Process in chunks, not all-at-once
         use GROUP BY in SQL (not Python)
```

## Security Considerations

### Data Integrity

```
✓ SHA256 checksums prevent tampering
✓ PostgreSQL ACID transactions
✓ Soft deletes preserve history
✓ Version tracking prevents data loss
```

### Access Control

```
Recommended:
  - Use PostgreSQL role-based access
  - Separate read-only and read-write users
  - Audit log all deletions
  - Backup database regularly
```

### Sensitive Data

```
⚠ Checksums can identify identical files
⚠ File paths are not encrypted at rest
⚠ Git commit hashes are public

If sensitive:
  - Hash the file paths too
  - Encrypt database column
  - Use PostgreSQL pgcrypto
```

## Maintenance Operations

### Regular Tasks

```sql
-- Weekly: Cleanup orphaned versions
DELETE FROM file_versions WHERE file_id NOT IN (SELECT id FROM files);

-- Monthly: Recalculate compression stats
REFRESH MATERIALIZED VIEW compression_stats;

-- Quarterly: Reindex for performance
REINDEX DATABASE vcrud;

-- Annually: Archive old branches
DELETE FROM files WHERE branch_id = (SELECT id FROM branches WHERE branch_name = 'old-branch');
```

### Backup Strategy

```bash
# Daily backup
pg_dump -U vcrud_user vcrud > backup_$(date +%Y%m%d).sql

# Restore from backup
psql -U vcrud_user vcrud < backup_20260702.sql
```

## Future Enhancements

### Planned Features

1. **Web UI** - Browse branches, view stats, compare
2. **GraphQL API** - Complex queries without SQL
3. **Streaming Upload** - Handle multi-TB repositories
4. **Cloud Storage** - Sync metadata to S3/GCS
5. **Machine Learning** - Predict compression ratios
6. **Webhooks** - Auto-index on Git push
7. **Replication** - Multi-region PostgreSQL
8. **Archival** - Move old files to Glacier

### Extension Points

```python
# Custom compression algorithm
class CustomCompression:
    def compress(self, data):
        # Implement zstd, brotli, etc.
        pass

# Custom indexing strategy
class SmartIndexer:
    def should_compress(self, file):
        # Skip incompressible files
        pass

# Custom analysis
class CustomAnalysis:
    def predict_bloat(self):
        # ML-based recommendations
        pass
```

---

This architecture ensures:
- **Scalability** - PostgreSQL handles millions of files
- **Integrity** - Git-backed versioning prevents data loss
- **Performance** - Strategic indexing keeps queries fast
- **Flexibility** - Can extend with custom algorithms
