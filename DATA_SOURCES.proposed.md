
```markdown
# DATA_SOURCES.md - global-stock-screener

Status as of 2026-11-08. Educational / research use only; not investment advice.
Every row says what we hold, under what terms, how it was collected and how stale it is.
"Private only" means: do not publish in a public repository.

| Tier | Meaning |
|---|---|
| A | Open licence or government open data; may be redistributed with attribution |
| B | Free to read, redistribution not granted; keep out of public repos, re-fetch per user |
| C | Third-party terms forbid copying/redistribution; private only, candidate for removal |

## 1. Prices (OHLCV)

### 1.1 Yahoo Finance via yfinance (Tier C)
- Publisher: Yahoo (Yahoo Finance). Library: `yfinance` (unofficial).
- URL: https://finance.yahoo.com ; terms: https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html
- Terms: API terms prohibit selling, sharing, transferring or sublicensing the data; personal use only.
- Fields: Date, Open, High, Low, Close (split-adjusted; Adj Close not stored), Volume, Symbol.
- Coverage: AU BR CA CH DE DK EU FI HK SA SE SG TW UK ZA in `cache_seed/ltm/`; CN EU HK IN JP KR US in `compact/*_2025plus.parquet`.
- Window: ltm 2025-06-26..2026-06-29; compact 2025-01-02..2026-07-23.
- Refresh: manual / pipeline run; not automatic. Stale by 3.5+ months.
- Caveats: 312 negative-price rows (KR `097780.KQ`), 163 rows > 1e7 in US (`AZLUY`), zero-volume rows 11-32% in thin markets, adjusted-price artefacts after splits.
- Collection: `data_sources.py` (yfinance download, Stooq fallback), `fetch_market_ohlc.py`, `compact/build_compact.py`.

### 1.2 Stooq (Tier B, unverified terms)
- URL: https://stooq.com . Fallback when Yahoo rate-limits. Terms not reviewed.

### 1.3 NSE and BSE bhavcopy (Tier B)
- Publisher: NSE (https://www.nseindia.com), BSE (https://www.bseindia.com).
- Terms: NSE disclaimer permits research-oriented download free of cost within a 2 GB aggregate threshold; no redistribution grant. BSE terms not confirmed.
- Fields: OHLCV, trades, delivery quantity and percent (full bhavcopy), series.
- Coverage: IN `compact/IN_2025plus.parquet` 2025-06-18..2026-07-22, 7,841 symbols (includes debt series and ETFs; filter by series EQ / ISIN prefix INE for equities).
- Refresh: daily if `update_bhavcopy_daily.py` is scheduled.
- Caveats: raw close (unadjusted splits, e.g. GOLDBEES unit split); 1,615 symbols have no bars since 2026-06-22.
- Collection: `bhavcopy_history.py`, `bhavcopy_store.py` (LMDB), `update_bhavcopy_daily.py`.

## 2. Fundamentals

### 2.1 SEC EDGAR XBRL (Tier A)
- Publisher: US SEC. URLs: https://data.sec.gov/api/xbrl/companyfacts/ , https://data.sec.gov/submissions/ .
- Terms: US government public information; fair-access (declared User-Agent with contact, <= 10 requests/s).
- Fields (21 cols in `fundamentals_history/US.parquet`): fy_end, filed, equity, cfo, ebit, total_assets, current_assets, revenue, net_income, shares, debt.
- Coverage: 4,597 tickers, 111,949 rows, fy_end 1987..2029 (12 rows are forward-dated and should be dropped).
- Refresh: collector `sec_history_collector.py` on demand.
- Caveats: revenue tag choice (ASC 606 subset vs total) changed results in the sister research repo; pre-2009 coverage is thin; fiscal-year labels can be forward-dated.
- Collection: `sec_fundamentals.py`, `sec_history_collector.py`, `sec_sic_collector.py` (SIC sample of 250, `reference_seed/sec_sic_US.csv`).

### 2.2 screener.in (Tier C)
- Publisher: Screener (https://www.screener.in). Terms: https://www.screener.in/guides/terms/ (personal, non-commercial viewing only).
- What we hold: 26 public-screen snapshots (`cache_seed/public_screens/`), per-company export-derived history (`IN_screener_only_backup.parquet`, 14,162 rows 2004..2026; `IN.parquet` rows with source=screener_in), shareholding pattern.
- Units: Rs crore (median net income 49.3), unlike yfinance rows (absolute INR). Normalise per `source` before use.
- Refresh: manual; authenticated session required (`screener_in_auth.py`).
- Caveats: IP throttling; quarterly-only for some fields; only about 3 years of shareholding available.

### 2.3 Trendlyne (Tier C)
- Terms: https://www.trendlyne.com/terms/ forbids redistribution and machine-readable database use without written permission. Used only as a private input.

### 2.4 NSE corporate results (Tier B)
- `fundamentals_history/IN_nse_results.parquet` 1,934 rows, filed 2018-08-03..2025-03-11; collected by `collect_nse_results.py`.

### 2.5 yfinance fundamentals (Tier C)
- `IN_yfinance.parquet` 4,008 rows, fy_end 2024-12-31..2026-06-30; absolute INR. Short history, annual only.

### 2.6 OpenDART, EDINET, Eastmoney (Tier B/unknown)
- KR (`KR.parquet`, `KR_dart_joined.parquet`), JP (`JP.parquet`), CN (`CN.parquet`). Read each publisher's terms and fill in before publishing.
- SE, SG, BR, CH tables hold 4-16 rows and should be treated as not covered.

## 3. Universes and reference

### 3.1 Exchange universe lists (Tier B)
- NASDAQ Trader, JPX, KRX, SGX, Euronext, Eastmoney, NSE EQUITY_L.csv -> `data/global_universe/*.csv` (25 markets, 30,256 rows in master), via `universe_sources.py`.
- Keep ticker, name, exchange only. US lists include rights/warrants/units; filter before use.

### 3.2 Index constituent tags (`data/europe_broad_list.csv`) (Tier C)
- Index labels (FTSE, DAX, CAC, IBEX, OMX etc.) belong to the index providers; source was Wikipedia (CC BY-SA 4.0). Recommend removing the `index` column.

### 3.3 Damodaran (NYU Stern) (Tier A/B)
- https://pages.stern.nyu.edu/~adamodar/ ; beta, margin, PE, ROE by industry (96 rows) and company list (48,156 rows). Cite the author; company-level file provenance unverified.

### 3.4 Kenneth French Data Library (Tier A/B)
- https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html ; FF3 monthly 1,198 rows. Cite Fama and French; prefer runtime download.

### 3.5 Wikipedia exchange list (Tier A, CC BY-SA 4.0)
- Basis of `EXCHANGE_COVERAGE.md` and `data/curated/exchange_reference.parquet`. Attribution and share-alike required.

## 4. Derived datasets (own work)
- `cache_seed/liquidity_index.parquet`, `market_liquidity.parquet`, `market_performance_5y.parquet`, `global_highlights.parquet`, `compact/liquidity_filters.parquet`, `reports/reward_*.csv`. Inherit the terms of section 1-2 inputs.

## 5. Open items before any publication
1. Remove Tier C files or move to a private companion repo.
2. Add `LICENSE` (code) and a data NOTICE with attributions (SEC, Wikipedia, Damodaran, French).
3. Fix units in `IN.parquet`, drop forward-dated US rows, filter negative/absurd prices, remove bonds from IN panel.
4. Refresh stale panels (last bar 2026-07-23).
```
