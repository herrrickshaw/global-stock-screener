#!/usr/bin/env python3
"""
sec_sic_collector.py — official SIC industry code + exchange per US ticker from SEC
EDGAR's submissions API (data.sec.gov/submissions/CIK##########.json).

Fills DATA_SOURCES.md untapped-win #3 (sector/industry classification) for US names
with a keyless, regulator-issued classification (SIC), as a cross-check/alternative to
the best-effort yfinance sector in sector_map.py. Needs only a contact User-Agent.

Output: reference_seed/sec_sic_US.csv (ticker, cik, name, sic, sic_description,
exchange, category, state_of_inc, fiscal_year_end). Existing files are NEVER touched;
re-runs merge into this one file only, skipping tickers already collected.

  python3 sec_sic_collector.py --limit 250          # every Nth ticker of the US universe
  python3 sec_sic_collector.py --tickers AAPL MSFT
"""
import argparse
import os
import time

import pandas as pd
import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE = os.path.join(_HERE, "data", "global_universe", "US.csv")
OUT = os.path.join(_HERE, "reference_seed", "sec_sic_US.csv")
_UA = {"User-Agent": "market-research umashankartd1991@gmail.com"}  # SEC requires a contact
_RATE = 0.13  # ~8 req/s (SEC allows 10)
COLS = ["ticker", "cik", "name", "sic", "sic_description", "exchange",
        "category", "state_of_inc", "fiscal_year_end"]


def ticker_cik():
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_UA, timeout=30)
    r.raise_for_status()
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}


def fetch(ticker, cik):
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_UA, timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    ex = d.get("exchanges") or []
    return {"ticker": ticker, "cik": cik, "name": d.get("name"), "sic": d.get("sic"),
            "sic_description": d.get("sicDescription"), "exchange": ex[0] if ex else None,
            "category": d.get("category"), "state_of_inc": d.get("stateOfIncorporation"),
            "fiscal_year_end": d.get("fiscalYearEnd")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--tickers", nargs="*")
    a = ap.parse_args()
    cmap = ticker_cik()
    if a.tickers:
        want = [t.upper() for t in a.tickers]
    else:
        uni = [t.upper() for t in pd.read_csv(UNIVERSE, keep_default_na=False)["yf_ticker"].astype(str)]
        uni = [t for t in uni if t in cmap]
        step = max(1, len(uni) // a.limit)
        want = uni[::step][: a.limit]  # deterministic stratified sample, low volume
    have = pd.read_csv(OUT, dtype=str) if os.path.exists(OUT) else pd.DataFrame(columns=COLS)
    done = set(have["ticker"])
    rows = []
    for t in want:
        if t in done or t not in cmap:
            continue
        try:
            row = fetch(t, cmap[t])
        except Exception:
            row = None
        if row:
            rows.append(row)
        time.sleep(_RATE)
    out = pd.concat([have, pd.DataFrame(rows, columns=COLS)], ignore_index=True)
    out.to_csv(OUT, index=False)
    print(f"requested {len(want)}, new {len(rows)}, total {len(out)}, "
          f"sic populated {out['sic'].notna().sum()} -> {OUT}")


if __name__ == "__main__":
    main()
