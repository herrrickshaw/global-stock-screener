#!/bin/bash
# morning_dashboard.sh
# ====================
# Daily 08:30 job: publish the repo activity dashboard onto a fresh dated branch
# and email it. Each run creates/updates branch  dashboard/YYYY-MM-DD  off the
# latest origin/mailer, snapshots the rendered HTML under dashboards/, keeps the
# integrity manifest valid, pushes the branch, and sends the dashboard email.
#
# Install via launchd (see schedule/com.screener.dashboard.plist) or cron:
#   30 8 * * * /Users/umashankar/Downloads/code/python_files/schedule/morning_dashboard.sh
#
# Requires GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO in the repo .env to actually
# send; otherwise the HTML is saved and still committed to the dated branch.
set -euo pipefail

REPO="/Users/umashankar/Downloads/code/python_files"
PYTHON="${PYTHON:-python3}"
DATE="$(date +%Y-%m-%d)"
BRANCH="dashboard/${DATE}"
WT="/tmp/dashboard-${DATE}"
LOG="${HOME}/dashboard-mailer.log"

exec >>"$LOG" 2>&1
echo "===== $(date '+%F %T')  morning dashboard: ${BRANCH} ====="

cd "$REPO"
# committer identity + skip the flaky LFS lock-verify API on push (unattended run)
git config user.name  >/dev/null 2>&1 || git config user.name  "herrrickshaw"
git config user.email >/dev/null 2>&1 || git config user.email "umashankartd1991@gmail.com"
git config lfs.locksverify false
git fetch origin --quiet

# fresh worktree on a new dated branch off the latest mailer branch
rm -rf "$WT"
git worktree add -B "$BRANCH" "$WT" origin/mailer
cd "$WT"
git config lfs.locksverify false

# build + send (or save HTML if no creds); non-fatal if the mailer hiccups
"$PYTHON" repo_dashboard.py --market IN US || echo "  dashboard build reported an issue (continuing)"

# snapshot the rendered dashboard onto the branch
mkdir -p dashboards
cp results/repo_dashboard.html "dashboards/dashboard_${DATE}.html"
cp results/repo_dashboard.txt  "dashboards/dashboard_${DATE}.txt" 2>/dev/null || true

# keep integrity manifest + dependency map in sync so the branch stays conformant
git add -A
"$PYTHON" dep_map.py >/dev/null 2>&1 || true
"$PYTHON" integrity.py --generate >/dev/null 2>&1 || true
git add -A

git commit -m "chore(dashboard): snapshot ${DATE}" || echo "  nothing to commit"

# push with a few retries — the LFS lock API / network can time out transiently
for attempt in 1 2 3; do
    if git push -u origin "$BRANCH" --force; then
        echo "  pushed on attempt ${attempt}"
        break
    fi
    echo "  push attempt ${attempt} failed; retrying in 20s"
    sleep 20
done

cd "$REPO"
git worktree remove --force "$WT"
echo "  done: ${BRANCH}"
