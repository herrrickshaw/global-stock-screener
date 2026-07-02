# Using vCRUD from feature/vcrud-system-tracker Branch

**This is the recommended approach for team collaboration.**

The vCRUD system lives on its own dedicated branch. Use it from any other branch without merging code duplicates.

## Quick Start (2 Minutes)

### From Any Branch, Analyze Your Work

```bash
# You're on your feature branch (e.g., feature/darvas-interpreter)
git checkout feature/vcrud-system-tracker

# Run analysis on your branch
python find_duplicates_standalone.py

# See what files matter most
python vcrud_cli.py hints --branch your-feature-branch

# Compare with main
python vcrud_cli.py compare --branch1 main --branch2 your-feature-branch

# Back to your work
git checkout -
```

That's it. No merging, no code duplication.

## Why This Approach?

✓ **Single Source of Truth** - vCRUD code lives in one place  
✓ **No Duplication** - Each branch stays lean  
✓ **Easy Updates** - Fix/improve vCRUD once, everyone benefits  
✓ **Team Collaboration** - All branches use the same tools  
✓ **Zero Merge Conflicts** - vCRUD never conflicts with your code  

## Common Workflows

### Workflow 1: Analyze Before Merging Your Branch

```bash
# You're on: feature/your-work
# Task: Check file impacts before PR to main

# Step 1: Stash your work
git stash

# Step 2: Switch to vCRUD
git checkout feature/vcrud-system-tracker

# Step 3: Analyze your branch
python find_duplicates_standalone.py

# Or with database (if set up):
python vcrud_cli.py compare --branch1 main --branch2 feature/your-work
python vcrud_cli.py stats --branch feature/your-work

# Step 4: Return to your work
git checkout -
git stash pop
```

### Workflow 2: Optimize Your Branch's Files

```bash
# Find what needs optimization
git checkout feature/vcrud-system-tracker

python vcrud_cli.py stats --branch global-expansion-screener-v3.1

# Output:
# Total size: 184.8 MB
# Compressed: ~74 MB
# Avg ratio: 40%

# See what doesn't compress well
python vcrud_cli.py optimize --branch global-expansion-screener-v3.1

# Decision: Archive or move those files to LFS
git checkout global-expansion-screener-v3.1
# ... optimize your files ...
```

### Workflow 3: Find Duplicates Before Code Review

```bash
# Pull latest vCRUD
git fetch origin feature/vcrud-system-tracker:feature/vcrud-system-tracker

# Switch to it
git checkout feature/vcrud-system-tracker

# Find duplicates across all branches
python find_duplicates_standalone.py

# Output: Shows which files are identical across branches
# Use this in PR review: "We can deduplicate these 5 files"

git checkout your-branch
```

### Workflow 4: Create a Git Alias for Quick Access

Add this to your git config:

```bash
git config --global alias.vcrud '!git stash && git checkout feature/vcrud-system-tracker && python find_duplicates_standalone.py && git checkout - && git stash pop'
```

Then use it like:
```bash
git vcrud  # Analyzes duplicates in current branch and returns
```

## For Each Branch Type

### Feature Branches (darvas, scanner-optimise, geography)

```bash
# Before submitting PR to main:
git fetch origin feature/vcrud-system-tracker
git checkout feature/vcrud-system-tracker

python vcrud_cli.py compare --branch1 main --branch2 feature/your-branch
# What files did you add/remove?

python find_duplicates_standalone.py
# Did you accidentally duplicate cache files?

git checkout your-branch
# Include findings in PR description
```

### Data Branches (global-expansion-screener)

```bash
# Before pushing massive commits:
git checkout feature/vcrud-system-tracker

python vcrud_cli.py stats --branch global-expansion-screener-v3.1
python vcrud_cli.py optimize --branch global-expansion-screener-v3.1

# Decision: Is this data bulk worth it? Should we use LFS?
git checkout your-branch
```

### Release Branches

```bash
# Before release, check file bloat:
git checkout feature/vcrud-system-tracker

python find_duplicates_standalone.py
# Remove unnecessary duplicates before release

git checkout release/v1.0
# Clean up and tag
```

## Setup (One-Time)

### Minimal (Standalone Tool)

```bash
# Just need Git and Python 3.9+
# Nothing else required

# Fetch the branch once
git fetch origin feature/vcrud-system-tracker
```

### Full System (With Database - Optional)

```bash
# Only if you want advanced features like git-backed versioning

# Install PostgreSQL
brew install postgresql@16
brew services start postgresql@16

# Create database
psql postgres -c "CREATE DATABASE vcrud; CREATE USER vcrud_user WITH PASSWORD 'password'; GRANT ALL ON DATABASE vcrud TO vcrud_user;"

# Install dependencies
pip install -r requirements_vcrud.txt
```

## Available Commands

When on `feature/vcrud-system-tracker`:

```bash
# Find duplicates (no DB needed)
python find_duplicates_standalone.py

# List files on branch
python vcrud_cli.py list --branch main

# Get statistics
python vcrud_cli.py stats --branch global-expansion-screener-v3.1

# Get caching hints
python vcrud_cli.py hints --branch main

# Compare branches
python vcrud_cli.py compare --branch1 main --branch2 feature/x

# File version history (needs DB)
python vcrud_cli.py history --file myfile.py --branch main

# Optimization report
python vcrud_cli.py optimize --branch main

# Export to JSON
python vcrud_cli.py export --branch main -o report.json
```

See `VCRUD_CHEATSHEET.md` for complete command list.

## Shell Shortcuts

### Create Helper Functions

Add to your `~/.zshrc` or `~/.bash_profile`:

```bash
# Quick duplicate check from any branch
vcrud-check() {
  local branch=$(git rev-parse --abbrev-ref HEAD)
  git stash
  git checkout feature/vcrud-system-tracker 2>/dev/null || git fetch origin feature/vcrud-system-tracker
  python find_duplicates_standalone.py
  git checkout "$branch"
  git stash pop 2>/dev/null
}

# Compare your branch to main
vcrud-compare() {
  local branch=$(git rev-parse --abbrev-ref HEAD)
  git checkout feature/vcrud-system-tracker 2>/dev/null || git fetch origin feature/vcrud-system-tracker
  python vcrud_cli.py compare --branch1 main --branch2 "$branch"
  git checkout "$branch"
}

# Get stats for your branch
vcrud-stats() {
  local branch=$(git rev-parse --abbrev-ref HEAD)
  git checkout feature/vcrud-system-tracker 2>/dev/null || git fetch origin feature/vcrud-system-tracker
  python vcrud_cli.py stats --branch "$branch"
  git checkout "$branch"
}

# Usage:
# vcrud-check      # Find duplicates in current branch
# vcrud-compare    # Compare current branch to main
# vcrud-stats      # Get file stats for current branch
```

Then reload:
```bash
source ~/.zshrc
```

## Team Workflow Example

### Team Member A (Working on feature/darvas)

```bash
# Check for duplicates before push
vcrud-check
# Output: No duplicates found, good to go

# Compare with main
vcrud-compare
# Output: Added 5 new Python files, removed 2 old ones

# Ready for PR
git push origin feature/darvas-interpreter
```

### Team Member B (Reviewing the PR)

```bash
# Switch to PR branch
git checkout feature/darvas-interpreter

# Analyze impact
vcrud-compare
# Output: Files changed are reasonable

# Check if review introduced bloat
vcrud-check

# Approve PR
```

### Team Lead (Managing Releases)

```bash
# Before release, check all branches for bloat
for branch in main feature/darvas feature/scanner feature/geography global-expansion-screener-v3.1; do
  echo "=== $branch ==="
  git checkout feature/vcrud-system-tracker
  python vcrud_cli.py stats --branch $branch
done

# Identify branches with duplication
# Request cleanup before release
```

## Troubleshooting

### "Module not found: psycopg2"

Use standalone tool instead (works without database):
```bash
python find_duplicates_standalone.py  # Always works
```

### Want to See vCRUD Without Switching Branches

```bash
# View files on vCRUD branch without checking it out
git ls-tree -r --name-only origin/feature/vcrud-system-tracker | head -20

# Download just one file
git show origin/feature/vcrud-system-tracker:VCRUD_README.md > temp_readme.md
```

### Need Latest Version

```bash
# Fetch latest from GitHub
git fetch origin feature/vcrud-system-tracker

# Switch and check for updates
git checkout feature/vcrud-system-tracker
git diff origin/main..origin/feature/vcrud-system-tracker
```

### Running Commands Without Switching Branches

```bash
# If you really don't want to switch branches, copy files temporarily:
git show origin/feature/vcrud-system-tracker:find_duplicates_standalone.py > /tmp/find_dupes.py
python /tmp/find_dupes.py

# Then delete
rm /tmp/find_dupes.py
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Check for Duplicates

on: [pull_request]

jobs:
  vcrud-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Fetch vCRUD branch
        run: git fetch origin feature/vcrud-system-tracker
      
      - name: Check duplicates
        run: |
          git checkout feature/vcrud-system-tracker
          python find_duplicates_standalone.py
      
      - name: Compare with main
        run: |
          python vcrud_cli.py compare --branch1 main --branch2 ${{ github.head_ref }}
```

## When to Check with vCRUD

| Scenario | Check | Command |
|----------|-------|---------|
| Before submitting PR | Yes | `vcrud-compare` |
| Before pushing to main | Yes | `vcrud-check` |
| Daily development | Optional | `vcrud-stats` |
| Before release | Yes | `vcrud-optimize` |
| Code review | Yes | `vcrud-compare` |
| Merging large branch | Yes | `vcrud-check` |

## FAQ

**Q: Do I need to merge vCRUD into my branch?**  
A: No. Just switch to the branch when you need it, then switch back.

**Q: Will using vCRUD affect my branch?**  
A: No. Switching branches doesn't modify your code, just changes what's checked out.

**Q: Can multiple people use vCRUD at the same time?**  
A: Yes. It's read-only analysis, no conflicts possible.

**Q: What if vCRUD gets updated?**  
A: `git fetch origin feature/vcrud-system-tracker` to get the latest.

**Q: Should we ever merge vCRUD into main?**  
A: Only if everyone wants it available in every branch by default. For now, referencing it is cleaner.

---

## TL;DR

```bash
# Using vCRUD from any branch:

git checkout feature/vcrud-system-tracker
python find_duplicates_standalone.py
git checkout -  # Back to your branch

# That's it. No merging, no code duplication.
```

**Branch:** `feature/vcrud-system-tracker`  
**GitHub:** https://github.com/herrrickshaw/global-stock-screener/tree/feature/vcrud-system-tracker
