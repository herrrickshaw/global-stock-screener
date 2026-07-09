#!/usr/bin/env python3
"""
backtest_piotroski_us.py — POINT-IN-TIME backtest of the Piotroski F-Score on US
equities, using SEC-EDGAR historical financials + the stored 10-year OHLCV.

Method (no look-ahead):
  • For each (ticker, fiscal-year) row in cache_seed/fundamentals_history/US.parquet,
    compute the 9-point Piotroski F-Score from year vs year-1 (all fields are from
    the 10-K, `filed` = date it became public).
  • ENTRY = first trading day on/after `filed` + 1; EXIT = HORIZON trading days later,
    priced from cache_seed/ltm/US.parquet. Forward return = exit/entry − 1.
  • Edge = mean forward return of a Piotroski band minus the mean of all scored rows.

Educational/research only. Survivorship caveat: ltm holds only currently-listed names.

  python3 backtest_piotroski_us.py                 # 126-day (~6mo) horizon
  python3 backtest_piotroski_us.py --horizon 252   # 1-year
"""
import argparse
import os

import numpy as np
import pandas as pd

BASE = os.path.expanduser("~/Downloads/code/python_files")
HIST = os.path.join(BASE, "cache_seed", "fundamentals_history", "US.parquet")
PRICES = os.path.join(BASE, "cache_seed", "ltm", "US.parquet")


def _piotroski(df):
    """Compute F-score per (ticker, fy_end) from year vs prior year (point-in-time)."""
    df = df.sort_values(["ticker", "fy_end"]).copy()
    g = df.groupby("ticker")

    def prev(col):
        return g[col].shift(1)

    ta, ta1 = df["total_assets"], prev("total_assets")
    ni = df["net_income"]
    roa = ni / ta
    roa1 = prev("net_income") / ta1
    cfo = df["cfo"]
    ca, cl = df["current_assets"], df["current_liabilities"]
    cr = ca / cl
    cr1 = prev("current_assets") / prev("current_liabilities")
    ltd, ltd1 = df["long_term_debt"], prev("long_term_debt")
    lev, lev1 = ltd / ta, ltd1 / ta1
    sh, sh1 = df["shares"], prev("shares")
    gm = df["gross_profit"] / df["revenue"]
    gm1 = prev("gross_profit") / prev("revenue")
    at = df["revenue"] / ta
    at1 = prev("revenue") / ta1

    f = (
        (roa > 0).astype(float)
        + (cfo > 0).astype(float)
        + (roa > roa1).astype(float)
        + ((cfo / ta) > roa).astype(float)
        + (lev < lev1).astype(float)
        + (cr > cr1).astype(float)
        + (sh <= sh1).astype(float)
        + (gm > gm1).astype(float)
        + (at > at1).astype(float)
    )
    # only rows with a real prior year (need the deltas) get a valid score
    df["F"] = np.where(ta1.notna(), f, np.nan)
    return df.dropna(subset=["F"])


def _forward_returns(scored, horizon):
    """Attach forward return: entry = first trading day after `filed`, exit = +horizon."""
    px = pd.read_parquet(PRICES, columns=["Date", "Close", "Symbol"])
    px["Date"] = pd.to_datetime(px["Date"])
    px = px.sort_values(["Symbol", "Date"])
    # per-symbol arrays of dates + closes for fast positional lookup
    by_sym = {
        s: (grp["Date"].to_numpy(), grp["Close"].to_numpy()) for s, grp in px.groupby("Symbol")
    }
    fwd = []
    for _, r in scored.iterrows():
        arr = by_sym.get(str(r["ticker"]).upper())
        if arr is None or not r.get("filed") or str(r["filed"]) == "9999-99-99":
            fwd.append(np.nan)
            continue
        dates, closes = arr
        entry_dt = np.datetime64(str(r["filed"])) + np.timedelta64(1, "D")
        i = int(np.searchsorted(dates, entry_dt))
        j = i + horizon
        if i < len(dates) and j < len(dates) and closes[i] > 0:
            fwd.append(closes[j] / closes[i] - 1.0)
        else:
            fwd.append(np.nan)
    scored = scored.copy()
    scored["fwd"] = fwd
    return scored.dropna(subset=["fwd"])


def main():
    ap = argparse.ArgumentParser(description="Point-in-time Piotroski backtest (US)")
    ap.add_argument(
        "--horizon", type=int, default=126, help="forward trading days (default 126 ≈ 6mo)"
    )
    args = ap.parse_args()
    if not os.path.exists(HIST):
        raise SystemExit(f"missing {HIST} — run sec_history_collector.py first")

    hist = pd.read_parquet(HIST)
    scored = _piotroski(hist)
    scored = _forward_returns(scored, args.horizon)
    base = scored["fwd"].mean()

    print(f"Piotroski F-Score backtest — US — {args.horizon}-day forward, point-in-time")
    print(
        f"  scored rows: {len(scored):,} | tickers: {scored['ticker'].nunique()} "
        f"| years: {pd.to_datetime(scored['fy_end']).dt.year.min()}–{pd.to_datetime(scored['fy_end']).dt.year.max()}"
    )
    print(f"  baseline mean forward return (all scored): {base*100:+.2f}%\n")
    print(f"  {'F band':<10}{'n':>7}{'mean fwd%':>11}{'edge pp':>10}{'win%':>7}")
    for lo, hi, label in [
        (8, 9, "strong 8–9"),
        (7, 9, "≥7"),
        (4, 6, "mid 4–6"),
        (0, 3, "weak 0–3"),
    ]:
        sub = scored[(scored["F"] >= lo) & (scored["F"] <= hi)]
        if len(sub):
            m = sub["fwd"].mean()
            print(
                f"  {label:<10}{len(sub):>7,}{m*100:>10.2f}%{(m-base)*100:>+9.2f}{(sub['fwd']>0).mean()*100:>6.1f}%"
            )
    # monotonicity check: mean fwd return by exact F score
    print("\n  by exact F:")
    tab = scored.groupby(scored["F"].astype(int))["fwd"].agg(["count", "mean"])
    for f, row in tab.iterrows():
        print(f"    F={f}: n={int(row['count']):>6,}  mean {row['mean']*100:+.2f}%")


if __name__ == "__main__":
    main()
