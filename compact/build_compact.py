#!/usr/bin/env python3
"""Build the compact storage snapshot: per-market OHLCV 2025→present.

Re-encodes the warehouse's recent window as ZSTD-19 parquet sorted by
(Symbol, Date) — sorted+zstd typically halves the size vs the snappy
originals — plus a small compact.duckdb catalog with coverage stats.
Re-run after any warehouse refresh; outputs are atomic replaces.

Run with /usr/bin/python3 (duckdb lives there, not the venv).
"""
import os, datetime
import duckdb

WH = os.path.expanduser("~/repos/global-market-data/warehouse/ohlcv")
HK_1Y = os.path.expanduser("~/repos/global-stock-screener/cache_seed/ltm/HK.parquet")
GAPFILL = os.path.expanduser("~/repos/global-market-data/warehouse/gapfill_ec2")  # merged later
OUT = os.path.dirname(os.path.abspath(__file__))
SINCE = "2025-01-01"

con = duckdb.connect()
sizes = {}
markets = sorted(d for d in os.listdir(WH) if os.path.isdir(f"{WH}/{d}"))
for mkt in markets:
    src = f"{WH}/{mkt}/year=*.parquet"
    extra = ""
    gp = f"{GAPFILL}/gapfill_{mkt}.parquet"
    if os.path.exists(gp):  # union in EC2 gap-fill rows once merged
        extra = f" UNION ALL SELECT Date, Symbol, Open, High, Low, Close, Volume FROM read_parquet('{gp}')"
    out = f"{OUT}/{mkt}_2025plus.parquet"
    con.execute(f"""
        COPY (
          SELECT Date, Symbol, Open, High, Low, Close, Volume FROM (
            SELECT * FROM read_parquet('{src}'){extra})
          WHERE Date >= DATE '{SINCE}'
          QUALIFY row_number() OVER (PARTITION BY Symbol, Date ORDER BY Volume DESC NULLS LAST) = 1
          ORDER BY Symbol, Date
        ) TO '{out}.tmp' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 19)""")
    os.replace(f"{out}.tmp", out)
    sizes[mkt] = os.path.getsize(out)

# HK: only the 1y panel exists until the EC2 backfill merges
if os.path.exists(HK_1Y):
    out = f"{OUT}/HK_2025plus.parquet"
    gp = f"{GAPFILL}/gapfill_hongkong.parquet"
    extra = (f" UNION ALL SELECT Date, Symbol, Open, High, Low, Close, Volume "
             f"FROM read_parquet('{gp}')") if os.path.exists(gp) else ""
    con.execute(f"""
        COPY (
          SELECT Date, Symbol, Open, High, Low, Close, Volume FROM (
            SELECT Date, Symbol, Open, High, Low, Close, Volume
            FROM read_parquet('{HK_1Y}'){extra})
          WHERE Date >= DATE '{SINCE}'
          QUALIFY row_number() OVER (PARTITION BY Symbol, Date ORDER BY Volume DESC NULLS LAST) = 1
          ORDER BY Symbol, Date
        ) TO '{out}.tmp' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 19)""")
    os.replace(f"{out}.tmp", out)
    sizes["HK"] = os.path.getsize(out)

# catalog duckdb: coverage stats over the compact set
cat = f"{OUT}/compact.duckdb"
if os.path.exists(cat):
    os.remove(cat)
cc = duckdb.connect(cat)
cc.execute(f"""CREATE TABLE coverage AS
    SELECT regexp_extract(filename, '([A-Z]+)_2025plus', 1) AS market,
           count(DISTINCT Symbol) AS symbols, count(*) AS rows,
           min(Date)::DATE AS from_date, max(Date)::DATE AS to_date
    FROM read_parquet('{OUT}/*_2025plus.parquet', filename=true) GROUP BY 1""")
cc.execute(f"CREATE TABLE build_meta AS SELECT '{datetime.datetime.utcnow().isoformat()}Z' AS built_at, '{SINCE}' AS since")
for r in cc.execute("SELECT * FROM coverage ORDER BY market").fetchall():
    print(f"  {r[0]:3s} {r[1]:6,} syms {r[2]:10,} rows  {r[3]} → {r[4]}")
cc.close()
total = sum(sizes.values()) + os.path.getsize(cat)
print(f"compact set: {total/1e6:.0f} MB "
      f"({', '.join(f'{m} {s/1e6:.0f}MB' for m, s in sorted(sizes.items()))})")
