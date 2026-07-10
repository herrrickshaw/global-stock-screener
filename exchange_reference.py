#!/usr/bin/env python3
"""
exchange_reference.py — daily data-freshness checklist across ALL exchanges.
============================================================================
Builds a single reference so stale market data is caught at a glance:

  data/curated/exchange_reference.parquet   one row per (market, exchange) with
      the ticker list, the universe-list update date, the scan-DATA update date,
      age in days, and a FRESH / STALE / UNIVERSE_ONLY / NO_DATA status.

  data/curated/daily_checklist_<date>.md    a human-readable ✅/⚠️ checklist.

Freshness has two layers:
  • universe_updated — when the ticker LIST for that exchange was last refreshed
    (mtime of the data/global_universe/<MKT>.csv it came from).
  • data_updated     — when the SCAN data (OHLC+fundamentals) for that market was
    last rebuilt (mtime of the latest scan workbook). Only US/EU/IN are scanned;
    other markets are UNIVERSE_ONLY (we track their tickers but don't scan yet).

Status rule: on a weekday, data older than STALE_AFTER_DAYS is STALE.

CLI:
  python3 exchange_reference.py            # build parquet + print checklist
  python3 exchange_reference.py --stale    # exit 1 if any scanned exchange is stale
"""
import argparse
import datetime
import glob
import os
import sys

import pandas as pd

BASE = os.path.expanduser("~/Downloads/code/python_files")
CURATED = os.path.join(BASE, "data", "curated")
UNIVERSE_GLOB = os.path.join(BASE, "data", "global_universe", "*.csv")

# market → scan workbook glob (data freshness). Markets absent here are UNIVERSE_ONLY.
SCAN_GLOBS = {
    "US": "us_full_scan/us_full_scan_*.xlsx",
    "EU": "european_scan/european_market_scan_broad_*.xlsx",
    "IN": "indian_full_scan/indian_full_scan_*.xlsx",
}
# Tidy the terse US exchange codes the universe file carries.
US_EXCH_FIX = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe BZX", "K": "Nasdaq"}
STALE_AFTER_DAYS = 1  # weekday scan data older than this = STALE


def _mtime_date(path):
    return (
        datetime.date.fromtimestamp(os.path.getmtime(path))
        if path and os.path.exists(path)
        else None
    )


def _latest(patt):
    f = sorted(glob.glob(os.path.join(BASE, patt)), key=os.path.getmtime)
    return f[-1] if f else None


def build_reference(today=None):
    """Return the per-(market,exchange) freshness DataFrame."""
    today = today or datetime.date.today()
    scan = {m: (_latest(g), _mtime_date(_latest(g))) for m, g in SCAN_GLOBS.items()}
    rows = []
    for f in sorted(glob.glob(UNIVERSE_GLOB)):
        df = pd.read_csv(f)
        market = os.path.splitext(os.path.basename(f))[0].upper()
        uni_date = _mtime_date(f)
        tcol = "yf_ticker" if "yf_ticker" in df.columns else df.columns[0]
        if "exchange" not in df.columns:
            df["exchange"] = market
        df["exchange"] = df["exchange"].astype(str).replace(US_EXCH_FIX)
        scan_wb, scan_date = scan.get(market, (None, None))
        for exch, g in df.groupby("exchange"):
            tickers = sorted(g[tcol].dropna().astype(str).unique())
            if scan_date:
                age = (today - scan_date).days
                status = "FRESH" if age <= STALE_AFTER_DAYS else "STALE"
                data_updated = scan_date.isoformat()
            else:
                age = (today - uni_date).days if uni_date else None
                status = "UNIVERSE_ONLY"
                data_updated = None
            rows.append(
                {
                    "market": market,
                    "exchange": exch,
                    "n_tickers": len(tickers),
                    "tickers": tickers,
                    "universe_source": os.path.relpath(f, BASE),
                    "universe_updated": uni_date.isoformat() if uni_date else None,
                    "scan_source": os.path.relpath(scan_wb, BASE) if scan_wb else None,
                    "data_updated": data_updated,
                    "age_days": age,
                    "status": status,
                    "checked": today.isoformat(),
                }
            )
    order = {"STALE": 0, "NO_DATA": 1, "FRESH": 2, "UNIVERSE_ONLY": 3}
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["status", "market", "exchange"], key=lambda s: s.map(order) if s.name == "status" else s
    ).reset_index(drop=True)


def write_parquet(df):
    os.makedirs(CURATED, exist_ok=True)
    out = os.path.join(CURATED, "exchange_reference.parquet")
    df.to_parquet(out, index=False)
    return out


_BADGE = {"FRESH": "✅", "STALE": "⚠️", "UNIVERSE_ONLY": "📋", "NO_DATA": "❌"}


def checklist_md(df, today):
    """Render a human-readable daily checklist (markdown)."""
    lines = [f"# 📋 Daily Data Freshness Checklist — {today.isoformat()}", ""]
    n_ex = len(df)
    stale = int((df["status"] == "STALE").sum())
    fresh = int((df["status"] == "FRESH").sum())
    uni = int((df["status"] == "UNIVERSE_ONLY").sum())
    lines.append(
        f"**{n_ex} exchanges** · ✅ {fresh} fresh · ⚠️ {stale} stale · 📋 {uni} universe-only "
        f"· {int(df['n_tickers'].sum()):,} tickers tracked"
    )
    if stale:
        names = ", ".join(df[df["status"] == "STALE"]["exchange"].tolist())
        lines.append(f"\n> ⚠️ **STALE — refresh needed:** {names}")
    lines.append(
        "\n| Status | Market | Exchange | Tickers | Data updated | Age (d) | List updated |"
    )
    lines.append("|---|---|---|---:|---|---:|---|")
    for _, r in df.iterrows():
        badge = _BADGE.get(r["status"], "")
        age = "" if pd.isna(r["age_days"]) else int(r["age_days"])
        lines.append(
            f"| {badge} {r['status']} | {r['market']} | {r['exchange']} | {r['n_tickers']:,} | "
            f"{r['data_updated'] or '—'} | {age} | {r['universe_updated'] or '—'} |"
        )
    return "\n".join(lines) + "\n"


def run(today=None, write=True):
    today = today or datetime.date.today()
    df = build_reference(today)
    if df.empty:
        print("No universe files found under data/global_universe/*.csv")
        return df, None
    pq = write_parquet(df) if write else None
    md = checklist_md(df, today)
    if write:
        md_path = os.path.join(CURATED, f"daily_checklist_{today.isoformat()}.md")
        open(md_path, "w").write(md)
    # concise console checklist
    print(md.split("\n| Status")[0])  # header + summary + stale line
    print(f"\nparquet → {os.path.relpath(pq, BASE) if pq else '(not written)'}")
    return df, pq


def main():
    ap = argparse.ArgumentParser(description="Daily exchange data-freshness reference + checklist")
    ap.add_argument("--stale", action="store_true", help="exit 1 if any scanned exchange is STALE")
    ap.add_argument("--no-write", action="store_true", help="print only; don't write files")
    args = ap.parse_args()
    df, _ = run(write=not args.no_write)
    if args.stale and not df.empty and (df["status"] == "STALE").any():
        sys.exit(1)


if __name__ == "__main__":
    main()
