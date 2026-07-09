#!/bin/bash
# daily_pipeline.sh — token-free Daily Market Report, orchestrated by the ETL pipeline.
# =====================================================================================
# Runs entirely in local Python (no Claude / no LLM tokens). The heavy fetching
# (India EOD, combined reports, European broad scan, Darvas fragments) is the
# EXTRACT layer; etl_pipeline.py then does the structured Extract(reuse) →
# Transform (curated parquet data lake) → Load (build report + email + manifest).
#
# Usage:
#   ./daily_pipeline.sh              # refresh + curate + build + EMAIL (needs Gmail creds)
#   ./daily_pipeline.sh --draft      # same, but save the report only (no email)
#
# Credentials (only needed to actually send) via environment:
#   GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO   (Google App Password)
# Without them the report is still built + saved to ~/Downloads.
#
# Schedule: com.umashankar.dailybrief.plist (launchd, macOS) runs this daily.
# Legacy 7-step pipeline preserved as daily_pipeline.legacy.sh.
set -uo pipefail
cd "$(dirname "$0")"
PY=python3
LOG="daily_pipeline_$(date +%Y%m%d).log"

# --draft (or --gmail-draft, --no-send) → build/save but do not email
SEND_FLAG=""
for a in "$@"; do
  case "$a" in
    --draft|--gmail-draft|--no-send) SEND_FLAG="--no-send" ;;
  esac
done

{
  echo "=== Daily ETL pipeline $(date) ==="

  echo "[extract] India EOD refresh + IN/US combined reports (fundamentals + street talk)"
  $PY bhavcopy_history.py 400                       || echo "  bhavcopy refresh failed (using cache)"
  $PY scan_bhavcopy.py                              || echo "  India scan failed (using cache)"
  $PY daily_combined_report.py --market IN --html   || echo "  IN combined report failed"
  $PY daily_combined_report.py --market US --html   || echo "  US combined report failed"

  echo "[extract] European broad scan (~1,000 stocks, 22 exchanges)"
  $PY full_european_market_scan.py --universe data/europe_broad_list.csv --label broad --batch 120 \
                                                    || echo "  EU scan failed (ETL will reuse latest)"

  echo "[extract] Darvas breakout fragments (IN + US)"
  $PY darvas_breakouts.py --market IN --top 15 > "$HOME/Downloads/in_darvas.html" 2>/dev/null \
                                                    || echo "  IN darvas fragment failed"
  $PY darvas_breakouts.py --market US --top 15 > "$HOME/Downloads/us_darvas.html" 2>/dev/null \
                                                    || echo "  US darvas fragment failed"

  echo "[etl] structured Extract → Transform (curate parquet) → Load (report + email + manifest)"
  $PY etl_pipeline.py --phase all --markets US,EU,IN $SEND_FLAG \
                                                    || echo "  etl_pipeline failed"

  echo "=== done $(date) ==="
} >> "$LOG" 2>&1
echo "pipeline complete — see $LOG"
