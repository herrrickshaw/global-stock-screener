# vCRUD Integration Guide for Other Branches

The vCRUD system has been committed to **`feature/vcrud-system-tracker`** branch on GitHub. Use it in any of your branches.

## Quick Integration (3 Ways)

### Way 1: Merge the Branch (Recommended)

Pull vCRUD into your feature branch and keep it updated:

```bash
# From your feature branch
git merge feature/vcrud-system-tracker

# Or cherry-pick specific commits
git cherry-pick 4778893
```

### Way 2: Reference from Shared Branch

Keep vCRUD on a separate branch and reference it:

```bash
# In your feature branch, create symlinks
ln -s ../feature/vcrud-system-tracker/db_handler.py db_handler.py
ln -s ../feature/vcrud-system-tracker/vcrud_cli.py vcrud_cli.py
```

### Way 3: Use vCRUD Before Merge

Run vCRUD tools before merging your branch to main:

```bash
# Switch to vCRUD system
git checkout feature/vcrud-system-tracker

# Run analysis
python vcrud_cli.py --db postgresql://... duplicates

# Results help decide merge strategy
git checkout your-feature-branch
```

## Files Included

```
feature/vcrud-system-tracker/
├── db_handler.py                 # PostgreSQL interface (480 lines)
├── vcrud_manager.py              # High-level CRUD manager (400 lines)
├── vcrud_cli.py                  # CLI with 15 commands (450 lines)
├── find_duplicates_standalone.py # No-DB duplicate finder (200 lines)
├── requirements_vcrud.txt        # Dependencies (psycopg2-binary)
├── VCRUD_README.md               # Complete overview
├── VCRUD_SETUP.md                # Installation guide
├── VCRUD_CHEATSHEET.md           # CLI command reference
└── VCRUD_ARCHITECTURE.md         # Deep technical design
```

## Use Cases Per Branch Type

### Feature Branches (darvas, scanner-optimise, etc.)

```bash
# Before merging to main: analyze changes
git checkout feature/vcrud-system-tracker
python find_duplicates_standalone.py  # No DB needed

# See what files your feature adds/removes
python vcrud_cli.py compare --branch1 main --branch2 your-branch
```

### Data Branches (global-expansion-screener)

```bash
# Track cache file bloat
python vcrud_cli.py scan-branch --branch global-expansion-screener-v3.1

# Find duplicate parquet files
python find_duplicates_standalone.py

# Optimize before pushing
python vcrud_cli.py optimize --branch global-expansion-screener-v3.1
```

### CI/CD Integration

```bash
# In your CI script
git clone https://github.com/herrrickshaw/global-stock-screener.git
cd global-stock-screener
git checkout feature/vcrud-system-tracker

# Get retrieval hints for your branch
python vcrud_cli.py hints --branch main

# Only download essential files for faster CI
```

## Setup Requirements

### Minimal (Standalone - No DB)

```bash
# Just Python 3.9+
python find_duplicates_standalone.py

# No PostgreSQL, no dependencies
```

### Full System (With Database)

```bash
# 1. Install PostgreSQL (one-time)
brew install postgresql@16
brew services start postgresql@16

# 2. Create database
psql postgres -c "CREATE DATABASE vcrud; CREATE USER vcrud_user WITH PASSWORD 'password'; GRANT ALL ON DATABASE vcrud TO vcrud_user;"

# 3. Install dependencies
pip install -r requirements_vcrud.txt

# 4. Use vCRUD
python vcrud_cli.py scan-branch --branch main
```

## Common Commands Across Branches

```bash
# Find duplicates (no DB needed)
python find_duplicates_standalone.py

# List files on any branch
python vcrud_cli.py list --branch your-branch

# Compare your branch to main
python vcrud_cli.py compare --branch1 main --branch2 your-branch

# Check file sizes
python vcrud_cli.py stats --branch your-branch

# Export analysis to JSON
python vcrud_cli.py export --branch your-branch -o report.json
```

## Branch Integration Strategy

### Option A: Keep vCRUD Separate (Recommended for Shared Use)

```
main
  └── feature/vcrud-system-tracker (shared, never delete)
         ↓ (reference for analysis)
  ├── feature/darvas-interpreter
  ├── feature/scanner-optimise
  └── global-expansion-screener-v3.1
```

**Benefits:**
- Single source of truth for vCRUD code
- Easy to update/fix vCRUD for all branches
- No duplication across branches

**Usage:**
```bash
# From any branch, run vCRUD
git stash  # Save current work
git checkout feature/vcrud-system-tracker
python find_duplicates_standalone.py  # Analyze your branch
git checkout -  # Back to your branch
git stash pop
```

### Option B: Merge into All Branches

```bash
# In each feature branch
git merge feature/vcrud-system-tracker

# Now vCRUD tools are available locally
python vcrud_cli.py scan-branch --branch feature/darvas-interpreter
```

**Benefits:**
- Each branch is self-contained
- No need to switch branches

**Trade-off:**
- vCRUD code duplicated across branches
- Updates require re-merging into all branches

## Recommended: Merge into main First

```bash
# Create PR from vCRUD branch to main
git checkout main
git pull
git merge feature/vcrud-system-tracker
git push

# All future branches can use vCRUD
git checkout -b feature/your-work
python vcrud_cli.py scan-branch --branch your-work
```

## Examples for Your Project

### Example 1: Analyze global-expansion Before Merge

```bash
git checkout feature/vcrud-system-tracker

# Find duplicates in your work
python find_duplicates_standalone.py

# Output: Found 33.5 MB of duplicate cache files
# Decision: Clean up before merging to main
```

### Example 2: Compare darvas vs main

```bash
python vcrud_cli.py compare --branch1 main --branch2 feature/darvas-interpreter

# Shows exactly what files darvas adds/removes
# Helps PR review
```

### Example 3: Optimize CI/CD

```bash
# Which files matter most?
python vcrud_cli.py hints --branch main

# Output: Pre-fetch these 5 files (accounts for 80% of usage)
# Update CI config to download only those
```

### Example 4: Archive Old Cache Files

```bash
# Check compression stats
python vcrud_cli.py stats --branch global-expansion-screener-v3.1

# Find poorly-compressed files
python vcrud_cli.py optimize --branch global-expansion-screener-v3.1

# Move to Git LFS or archive
```

## Troubleshooting

### "No module named psycopg2"

Use standalone duplicate finder instead:
```bash
python find_duplicates_standalone.py  # Works without DB
```

### PostgreSQL not running

```bash
# Use standalone, or start PostgreSQL
brew services start postgresql@16

# Then initialize database
psql postgres -c "CREATE DATABASE vcrud; ..."
```

### Want to Update vCRUD in All Branches

```bash
# Update in feature/vcrud-system-tracker
git checkout feature/vcrud-system-tracker
# ... make changes ...
git push

# Then merge into main and other branches
git checkout main
git merge feature/vcrud-system-tracker
git push

# Other branches can pull the updates
git checkout feature/your-work
git merge main
```

## Next Steps

1. **Try It:** Run `python find_duplicates_standalone.py` (no setup needed)
2. **Explore:** Read VCRUD_CHEATSHEET.md for all commands
3. **Decide:** Merge into main or keep separate?
4. **Integrate:** Add vCRUD calls to your CI/CD pipeline

---

**Branch Location:** `feature/vcrud-system-tracker`

**GitHub Link:** https://github.com/herrrickshaw/global-stock-screener/tree/feature/vcrud-system-tracker

**Questions?** See VCRUD_README.md or VCRUD_SETUP.md
