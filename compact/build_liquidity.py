#!/usr/bin/env python3
"""Cross-market liquidity filters over the compact 2025+ OHLCV set.

Per ticker (trailing 126 trading days):
  adv_local     — median daily traded value, Close×Volume, local currency
  adv_usd       — same, USD-normalized (snapshot FX; screening precision only)
  pct_days      — fraction of the market's trading days the ticker traded
  zero_vol_pct  — share of its own rows with Volume==0
  amihud        — median |daily return| / traded value  (×1e9, USD)

Tiers (adv_usd): T1 ≥ $1M · T2 ≥ $100k · T3 ≥ $10k · T4 below.
Any ticker with pct_days < 0.60 is demoted to T4 regardless — a name that
doesn't trade most days isn't fillable whatever its occasional volume says.
(Motivated by the illiquidity research: %ADV is the binding constraint, and the
India "staleness" audit showed non-trading is the real long-tail regime.)

Outputs: liquidity_filters.parquet + `liquidity` table in compact.duckdb.
Run with /usr/bin/python3 after build_compact.py.
"""
import os
import duckdb

OUT = os.path.dirname(os.path.abspath(__file__))
WINDOW = 126

# FX snapshot 2026-07-23 (screening-grade). EU is per-suffix; .L quotes pence.
FX_USD = {"IN": 1/86.0, "US": 1.0, "CN": 1/7.16, "JP": 1/148.0,
          "KR": 1/1380.0, "HK": 1/7.80}
EU_SUFFIX_FX = {
    ".L": (1.29, 0.01),   # GBp: ×0.01 → GBP, then ×1.29 → USD
    ".ST": (1/10.6, 1), ".CO": (1/6.85, 1), ".OL": (1/10.9, 1),
    ".SW": (1.13, 1), ".WA": (1/3.93, 1),
}
EUR_USD = 1.08  # default for .PA/.AS/.BR/.MI/.MC/.LS/.IR/.HE/.F/.DE/.VI/.AT

con = duckdb.connect()
frames = []
for f in sorted(os.listdir(OUT)):
    if not f.endswith("_2025plus.parquet"):
        continue
    mkt = f.split("_")[0]
    if mkt == "EU":
        fx_case = "CASE " + " ".join(
            f"WHEN Symbol LIKE '%{suf}' THEN {rate * scale}"
            for suf, (rate, scale) in EU_SUFFIX_FX.items()
        ) + f" ELSE {EUR_USD} END"
    else:
        fx_case = str(FX_USD.get(mkt, 1.0))
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE t AS
    WITH cal AS (          -- the MARKET's last {WINDOW} trading days
      SELECT DISTINCT Date FROM read_parquet('{OUT}/{f}')
      ORDER BY Date DESC LIMIT {WINDOW}
    ), win AS (
      SELECT p.Symbol, p.Date, p.Close, p.Volume,
             p.Close * p.Volume AS traded_local,
             abs(p.Close / lag(p.Close) OVER (PARTITION BY p.Symbol ORDER BY p.Date) - 1) AS aret
      FROM read_parquet('{OUT}/{f}') p
      WHERE p.Date IN (SELECT Date FROM cal)
    )
    SELECT '{mkt}' AS market, Symbol,
           count(*) AS days_present,
           (SELECT count(*) FROM cal) AS market_days,
           count(*)::DOUBLE / (SELECT count(*) FROM cal) AS pct_days,
           avg(CASE WHEN Volume = 0 THEN 1 ELSE 0 END) AS zero_vol_pct,
           median(traded_local) AS adv_local,
           median(traded_local) * ({fx_case}) AS adv_usd,
           median(CASE WHEN traded_local > 0 THEN aret / (traded_local * ({fx_case})) END) * 1e9 AS amihud_e9,
           max(Date)::DATE AS last_date
    FROM win GROUP BY Symbol""")
    frames.append(con.execute("SELECT * FROM t").fetchdf())

import pandas as pd
liq = pd.concat(frames, ignore_index=True)
liq["tier"] = "T4"
liq.loc[liq.adv_usd >= 10_000, "tier"] = "T3"
liq.loc[liq.adv_usd >= 100_000, "tier"] = "T2"
liq.loc[liq.adv_usd >= 1_000_000, "tier"] = "T1"
liq.loc[liq.pct_days < 0.60, "tier"] = "T4"   # non-trading overrides value

out = f"{OUT}/liquidity_filters.parquet"
liq.to_parquet(out, index=False)
cc = duckdb.connect(f"{OUT}/compact.duckdb")
cc.execute("CREATE OR REPLACE TABLE liquidity AS SELECT * FROM liq")
cc.close()

print(liq.groupby(["market", "tier"]).size().unstack(fill_value=0).to_string())
print(f"\n{len(liq):,} tickers → {out} + compact.duckdb::liquidity")
