# Data sources — used capability & unused potential

Every external data source the system references, what we **currently use**, and the
**unused potential** each holds for future analysis. All sources are free/official.

> ⚠️ Educational / research only. Respect each provider's Terms of Service & rate limits.

---

## Price & volume (OHLCV)

### 1. NSE + BSE bhavcopy — `bhavcopy_history.py`, `bhavcopy_store.py`
- **Source:** `nse` lib (NSE EOD) + `bseindia.com/download/BhavCopy/Equity/` (BSE CSV)
- **Currently used:** daily OHLCV for the full IN equity universe → LTM/STM seeds; the official, rate-limit-free EOD path.
- **Unused potential:** the *full* bhavcopy carries **delivery quantity & delivery %**, number of trades, VWAP, series/segment, and 52-week high/low fields — none consumed yet. Delivery% is a strong accumulation/distribution signal; deliverable-turnover would sharpen the liquidity tiers and feed a "smart-money" screen.

### 2. Yahoo Finance — `data_sources.py` (`yfinance`)
- **Currently used:** daily OHLC for the 19 non-IN markets (close/high/low/volume) → returns, SMA, RSI.
- **Unused potential:** **splits & dividends** (total-return series), **intraday/60-min** bars, **sector/industry, market cap, shares outstanding, beta**, and basic **fundamentals (trailing P/E, forward P/E, margins)** are all in the yfinance payload but dropped — could give dividend-adjusted performance, cross-market sector rotation, and P/E without SEC/screener.

### 3. Stooq — `data_sources.py` (fallback)
- **Currently used:** OHLC fallback when Yahoo rate-limits.
- **Unused potential:** **index & FX history, commodities**, and long (20-yr+) daily histories — a free path to deepen the LTM well beyond the current ~1yr and to add macro/FX context.

---

## Fundamentals

### 4. SEC EDGAR (XBRL companyfacts) — `sec_fundamentals.py`
- **Source:** `data.sec.gov/api/xbrl/companyfacts`, `sec.gov/files/company_tickers*.json`
- **Currently used (US):** net income, revenue, ROE/ROA, CFO, EBIT, current ratio, debt, margins, asset turnover, shares, EPS growth → Piotroski, ROCE, Magic Formula, decision engine.
- **Unused potential:** the **full XBRL fact set** — segment revenue, R&D, capex history, inventory/receivables/payables (full CCC), share buybacks, deferred revenue, per-quarter series, **8-K/10-K filing dates & text** — enables quarterly-trend models, accrual/earnings-quality flags, and event studies around filings.

### 4b. SEC EDGAR submissions (SIC industry code) — `sec_sic_collector.py` (added 2026-10-17)
- **Source:** `data.sec.gov/submissions/CIK##########.json` (keyless; contact User-Agent only), ticker→CIK from `sec.gov/files/company_tickers.json`.
- **Verified:** live sample of 250 US tickers (deterministic every-Nth of `data/global_universe/US.csv`) at ~8 req/s; 250/250 responded, 239 carry a SIC code + description (114 distinct codes; 11 have none), plus exchange, filer category, state of incorporation, fiscal-year-end. Output: `reference_seed/sec_sic_US.csv` (30 KB). Run is a sample, NOT the full US universe; `--limit 7000` would take ~15 min.
- **Gap filled:** untapped-win #3 (sector/industry classification) for US, as a regulator-issued cross-check to the best-effort yfinance sector in `sector_map.py`. Not yet joined into any screen; SIC is coarse (e.g. "Blank Checks", "Finance Services") and is a current snapshot, not point-in-time.
- **Tried, no new gap filled:** NSE `sec_bhavdata_full_<date>.csv` (delivery %) -- already consumed by `delivery_signal.py`; a single curl from this session returned no HTTP response (connection failure), so not re-verified here. SEC `companyfacts` already used (#4).
- **Candidates not tested (no keyless fundamentals found):** ESMA/FCA registers hold entity/instrument reference data, not financials; not pursued.

### 5. screener.in — public screens — `screener_in.py`, `public_screens.py`
- **Currently used (IN):** 26 curated popular screens (Bull Cartel, Piotroski, Magic Formula, CCC, …) as validation ground-truth + the CCC metric.
- **Unused potential:** each screen page exposes **ROCE/ROE/OPM/sales & profit growth/P/E/dividend columns** we only partially parse; the **query definitions** themselves (login) encode analyst logic we could replicate; peer/sector pages give **sector medians** for relative valuation.

### 5b. Trendlyne — authenticated (`trendlyne_auth.py`)
- **Currently used (IN):** per-stock P/E, PB, ROE, ROA, debt/equity, dividend yield,
  OPM, revenue/profit growth, Piotroski, market cap — the primary IN fundamentals feed
  (higher throughput than screener.in's export). Creds via `.env` only.
- **Unused potential:** SWOT/DVM scores, shareholding & pledge trends, forecasts,
  results calendar, superstar-investor holdings.

### 6. screener.in — authenticated export + company page — `screener_in_auth.py`
- **Currently used (IN):** per-company Excel export → net income, ROE, ROCE, debt, growth for the promoted watchlist; **dividend amount** (2026-07-18: ported into `screener_history_collector.py`'s point-in-time `FIELDS` map — was already parsed by `company_financials()` but never wired into the PIT collector feeding `IN.parquet`). Company-page HTML → **promoter/FII/DII/public holding % + shareholder count**, quarterly, via `page_ratios()`'s `_parse_shareholding()` (2026-07-18) — reuses the SAME page fetch `page_ratios()` already made, no new network call.
- **CORRECTED 2026-07-18 (previous entry here was wrong):** the Excel export does **NOT** contain shareholding-pattern data — verified by inspecting all 6 sheets (Profit & Loss, Quarters, Balance Sheet, Cash Flow, Customization, Data Sheet) on a live, unblocked account; zero shareholding-related rows in any of them. The real source is the company HTML page's `id="shareholding"` section, not the export.
- **Still unresolved:** **promoter pledge %** specifically — checked 4 tickers (ABBOTINDIA, ZEEL, SUZLON, VODAFONEIDEA), zero `pledg*` occurrences in the static page HTML for any of them. Likely rendered via a separate AJAX call behind the "+" expand button (`Company.showShareholders(...)`), not present in the page source `requests.get()` returns. `decision_engine.py`'s `promoter_pledge` consumer remains genuinely unfed — do not populate it with promoter_holding or anything else that isn't actually pledge data.
- **Wired into the point-in-time collector (2026-07-19):** `screener_history_collector.py`'s `collect_ticker()` now calls `industry_and_shareholding_of()` (one consolidated company-page GET, reusing `parse_shareholding_dated()`) and does a no-lookahead as-of merge -- each fiscal year gets the latest shareholding quarter knowable by `fy_end + 90d` (this file's own documented reporting-lag default), never a future one. Full re-collection run: `dividend_amount` 48.5% populated, `promoter_holding`/`fii_holding`/`dii_holding`/`public_holding`/`num_shareholders` ~27-30% overall but 93.6% for fy_end>=2024 specifically -- the lower overall figure is structural (the company page only exposes a trailing ~3-year window, so older fiscal years are unreachable by design, not a gap). A real throttling bug was found and fixed along the way: the page fetch used to fire immediately after the export fetch with zero delay, which measured at ~5% success under sustained bulk load despite the same fetch working instantly in isolation -- fixed with a delay + one retry, verified 5%->100% on a live sample before the full run.
- **Unused potential:** the export's **10-year annual + quarterly sheets** (balance sheet, cash flow, ratios) still have untapped rows beyond what `FIELDS`/`_extract_annual()` currently map — no export-side shareholding/FII/DII to find, per the correction above.

### 7. Damodaran datasets — `reference_data.py`
- **Currently used:** company list + reference tables (beta, margins, P/E, ROE) as reference seeds.
- **Unused potential:** **industry cost of capital / ERP / country risk premia, tax rates, revenue multiples** — a ready-made framework for DCF/intrinsic-value scoring and country-risk-adjusted screening.

### 8. Fama-French — `reference_data.py`
- **Currently used:** FF3 factor table stored as a reference seed (not yet in signals).
- **Unused potential:** **factor regressions** (market/size/value, plus momentum/quality if FF5 added) → factor-exposure attribution per stock and factor-tilted portfolio construction.

---

## Universes & reference

### 9. Exchange universe feeds — `universe_sources.py`
- **Sources:** JPX (`jpx.co.jp`), KRX (`kind.krx.co.kr`), SGX (`api.sgx.com`), Euronext (`live.euronext.com`), Eastmoney (`push2.eastmoney.com`, China).
- **Currently used:** the list of tradeable tickers per market (to fetch OHLCV).
- **Unused potential:** these endpoints also carry **sector/industry classification, listing date, board/segment, free-float, index membership, and (SGX/Eastmoney) live quotes & fundamentals** — sector tagging alone would unlock cross-market sector-rotation and the doc's sector-boom detector for all 20 markets.

### 10. `investpy` — referenced in `universe_sources.py`
- **Currently used:** supplementary universe/listing lookups.
- **Unused potential:** **economic calendar, bonds, ETFs, indices, commodities, country macro** — a macro overlay for regime detection.

### 11. nsepython — `market_calendar.py`, `screener_in.py`
- **Currently used:** NSE trading-holiday list (calendar) + CCC screen helper.
- **Unused potential:** **live quotes, option chain / India VIX, bulk & block deals, FII/DII cash-segment flows, corporate actions/announcements, index constituents** — VIX for regime, bulk/block + FII flows for the doc's "smart-money" and sector-flow signals.

---

## News / sentiment (currently archived)

### 12. RSS + VADER — `archive/sentiment-and-research-experiments`
- **Currently used:** none on `main` (moved to an archive branch).
- **Unused potential:** headline **sentiment per ticker** (token-free) as a discovery/timing overlay; the doc's Layer-2 "policy score" (Budget/PLI mentions) could be built from the same feed.

---

## Summary — biggest untapped wins

| Rank | Opportunity | Source(s) | Enables |
|------|-------------|-----------|---------|
| 1 | **Delivery % / deliverable turnover** | bhavcopy full (1) | accumulation signal, sharper liquidity |
| 2 | **10-yr + quarterly fundamentals, promoter pledge** | screener.in export (6) | compounding & red-flag screens |
| 3 | **Sector/industry classification (all 20 mkts)** | universes (9), yfinance (2) | sector-rotation, boom-phase detector |
| 4 | **FII/DII flows, bulk/block deals, VIX** | nsepython (11) | smart-money & regime signals |
| 5 | **Dividend/split-adjusted total return** | yfinance (2), stooq (3) | correct long-horizon performance |
| 6 | **Factor regressions (FF)** | Fama-French (8) | factor attribution & tilts |
| 7 | **Deeper history (20-yr)** | stooq (3), SEC (4) | fills the 5-yr LTM, robust backtests |

See `DATA_AND_MODULES.md` (module guide) and `BLOOMBERG_SOURCES.md` (Bloomberg-equivalent map).
