# Backtest Data Collection Plan
**Phase 1: Quarterly Fundamentals → Phase 2: Daily Prices → Phase 3: Backtest Analysis**

**Status:** Framework ready, data collection strategy defined  
**Timeline:** 2-3 weeks for full dataset collection  
**Scope:** 60 representative companies × 5 years = 1,825 trading days each

---

## 🎯 PHASED DATA COLLECTION STRATEGY

### Phase 1: Quarterly Fundamentals (THIS WEEK)
**Goal:** Understand 5-year trends before diving into daily data

**Companies Selected (60 across sectors):**
- Technology (15): MSFT, NVDA, CRM, ADBE, AVGO, MSTR, FTNT, NET, DDOG, CRWD, SNOW, PANW, ORCL, AAPL, IBM
- Industrials (15): CAT, GE, LMT, BA, RTX, ISRG, ABB, EMR, DE, CARR, TT, IRM, WAFER, FLEX, LOGI
- Energy & Materials (12): CVX, COP, SLB, MPC, OKE, NUE, FCX, CF, ALB, LYB, DOW, HUN
- Transportation (6): DAL, UAL, ALK, NCLH, CCL, RCL
- Real Estate (8): PLD, DLR, EQIX, VICI, PSA, UMC, CCI, AMT
- Healthcare (8): JNJ, PFE, MRK, BIIB, LLY, BMY, AMGN, GILD

**Data Points per Company (20 Quarters = 5 Years):**
- Revenue trend
- Operating income & margin
- Net income & margin
- Total debt (short + long term)
- Operating cash flow
- Capex (capital expenditure)
- Free cash flow
- Shareholders' equity

**Metrics Calculated:**
```
1. Revenue CAGR (5-year)
   └─ Growth trajectory

2. Capex CAGR (5-year)
   └─ Expansion intensity

3. Debt CAGR (5-year)
   └─ Leverage trend

4. FCF Average
   └─ Cash generation

5. Debt-to-Equity (latest)
   └─ Balance sheet health

6. Operating Margin Trend (avg)
   └─ Profitability trajectory

7. Capex-to-Revenue (avg)
   └─ Capital intensity
```

**Trend Analysis Output:**
- Aggressive expanders (high capex + debt growth)
- Conservative expanders (capex + deleveraging)
- Stable operators (low capex growth)
- Profitability leaders (margin improvement)

---

### Phase 2: Daily Price Data (WEEK 2)

**Goal:** Collect 5 years of daily closing prices and returns

**Data Structure:**
```
For each company (60) × Trading days (1,825):
├─ Date
├─ Close price
├─ Daily return (%)
├─ 1-month moving average return
├─ 3-month moving average return
└─ 12-month rolling return (THE TARGET)
```

**Key Calculation:**
```
12-month rolling return = (Price_today / Price_12mo_ago - 1) × 100%

This is what we're trying to predict with MAIN vs KARZ weights
```

**Data Sources:**
- Primary: yfinance (free, 5-year history)
- Backup: pandas_datareader
- Fallback: Alpha Vantage API (if needed)

**Expected Output:**
- CSV file: 60 companies × 1,825 days = 109,500 price points
- Size: ~50-75 MB
- Fetch time: 30-60 minutes (with yfinance rate limiting)

---

### Phase 3: Data Merging (WEEK 2-3)

**Goal:** Align quarterly fundamentals with daily prices

**Merge Strategy:**
```
For each company:
├─ Load quarterly fundamentals (20 data points)
├─ Load daily prices (1,825 data points)
└─ Create merged dataset:
    ├─ Each quarter's metrics
    ├─ Daily returns in that quarter
    ├─ 1-year forward return (starting next quarter)
    └─ Key signal: (quarterly metrics) vs (12-month forward return)
```

**Data Quality Checks:**
- No NaN values in critical fields
- Date alignment (quarterly to annual returns)
- Outlier detection (extreme returns/metrics)
- Currency consistency
- Stock split adjustments

**Output Format:**
```
ticker, date, quarter, revenue, capex, debt, fcf, oi_margin, 
return_12m_forward, debt_to_equity, capex_intensity, ...
```

---

### Phase 4: Backtest Analysis (WEEK 3)

**Goal:** Compare MAIN vs KARZ weight performance

**Backtest Process:**
```
1. For each company, calculate composite score using MAIN weights
   ├─ debt_expansion: 20%
   ├─ capex_acceleration: 20%
   ├─ profit_reinvestment: 15%
   ├─ profitability_quality: 15%
   ├─ sustainability: 15%
   ├─ timing_alignment: 10%
   └─ leverage_health: 5%

2. For each company, calculate composite score using KARZ weights
   ├─ debt_expansion: 10% (reduced)
   ├─ capex_acceleration: 24% (increased)
   ├─ profit_reinvestment: 19% (increased)
   ├─ profitability_quality: 15% (unchanged)
   ├─ sustainability: 4% (reduced)
   ├─ timing_alignment: 4% (reduced)
   ├─ leverage_health: 2% (reduced)
   └─ fcf_generation: 22% (NEW - was missing!)

3. Generate BUY/SELL signals
   ├─ BUY: Score > 70th percentile
   └─ SELL: Score < 70th percentile

4. Evaluate prediction accuracy
   ├─ True Positives: BUY signal + actual outperformance
   ├─ False Positives: BUY signal but underperformed
   ├─ False Negatives: SELL signal but actually outperformed
   └─ True Negatives: SELL signal + actual underperformance

5. Calculate metrics
   ├─ Precision: TP / (TP + FP)
   ├─ Recall: TP / (TP + FN)
   ├─ F1 Score: 2 × (P × R) / (P + R)
   ├─ Accuracy: (TP + TN) / Total
   └─ Return Spread: Avg buy return - Avg sell return
```

---

## 📊 EXPECTED RESULTS

### MAIN Weights (Baseline)
```
Precision:  52-58% (of our buys, this % actually outperformed)
Recall:     45-52% (caught this % of winners)
F1 Score:   0.48-0.54
Return Spread: 2-3% (buy portfolio beats sell portfolio by 2-3%)
```

### KARZ Weights (Optimized)
```
Precision:  58-65% (+6-7pp improvement)
Recall:     52-60% (+7-8pp improvement)
F1 Score:   0.54-0.62 (+0.06-0.08 improvement)
Return Spread: 4-6% (+1.5-3pp improvement)
```

### Deployment Decision
```
✅ Deploy KARZ if:
   - F1 improvement > 0.05 (10% relative gain)
   - Precision improvement > 5pp
   - Return spread increases

⚠️  Deploy with caution if:
   - F1 improvement 0.02-0.05 (5-10% gain)
   - Need ongoing monitoring

❌ Keep MAIN weights if:
   - F1 unchanged or decreases
   - Cannot predict performance
```

---

## 🛠️ TECHNICAL IMPLEMENTATION

### Tools Required
1. **Data Collection:**
   - yfinance (free stock data)
   - pandas (data manipulation)
   - numpy (calculations)

2. **Data Storage:**
   - CSV format (portable, no dependencies)
   - Parquet format (compression, 30% size reduction)
   - SQLite (if querying needed)

3. **Backtest Engine:**
   - scikit-learn (F1, precision, recall)
   - scipy (statistical analysis)
   - matplotlib (visualization)

### Code Structure
```
quarterly_data_collector.py    → Fetch fundamentals
daily_price_collector.py        → Fetch prices
data_merger.py                  → Align & merge
backtest_runner.py              → Run backtest
backtest_analyzer.py            → Generate report
```

---

## 📈 TIMELINE

### Week 1 (This Week)
- [x] Create quarterly data collector
- [x] Create daily price collector
- [x] Create backtest framework
- [ ] Collect quarterly fundamentals (60 companies, 5 years)
- [ ] Generate trend analysis report

### Week 2
- [ ] Collect daily price data (1,825 days × 60 companies)
- [ ] Quality assurance on price data
- [ ] Handle missing data/stock splits
- [ ] Begin preliminary analysis

### Week 3
- [ ] Merge quarterly fundamentals with daily prices
- [ ] Run backtest on MAIN weights (baseline)
- [ ] Run backtest on KARZ weights (optimized)
- [ ] Generate comparison report

### Week 4
- [ ] Analyze results
- [ ] Decision: deploy or refine
- [ ] If deploying: merge KARZ → MAIN branch
- [ ] If refining: adjust weights and re-test

---

## 💾 DATA STORAGE PLAN

### Directory Structure
```
/backtest_data/
├─ quarterly/
│  ├─ raw/
│  │  ├─ MSFT_quarters.csv
│  │  ├─ NVDA_quarters.csv
│  │  └─ ...60 companies
│  └─ processed/
│     └─ quarterly_trends_5yr.csv
├─ daily/
│  ├─ raw/
│  │  ├─ MSFT_daily.csv
│  │  ├─ NVDA_daily.csv
│  │  └─ ...60 companies
│  └─ processed/
│     └─ daily_prices_merged.csv
├─ merged/
│  └─ backtest_input.csv (quarterly + daily)
└─ results/
   ├─ backtest_main_weights.csv
   ├─ backtest_karz_weights.csv
   └─ comparison_report.md
```

### File Sizes
```
Quarterly data (20 quarters × 60 cos):  ~3 MB
Daily data (1,825 days × 60 cos):       ~50-75 MB
Merged dataset:                         ~60-90 MB
Results & reports:                      ~5 MB
─────────────────────────────────────
TOTAL:                                  ~120-175 MB
```

---

## ✅ SUCCESS CRITERIA

### Data Collection
- [x] Framework created
- [ ] 60 companies selected (in progress)
- [ ] 5 years of quarterly data collected
- [ ] 5 years of daily data collected
- [ ] Data quality validated
- [ ] Datasets merged successfully

### Backtest Analysis
- [ ] MAIN weights baseline calculated
- [ ] KARZ weights calculated
- [ ] Metrics compared
- [ ] Report generated
- [ ] Deployment decision made

### Deployment
- [ ] If improved: merge to MAIN branch
- [ ] If improved: update production screener
- [ ] If improved: monitor quarterly performance
- [ ] If not: refine weights and re-test

---

## 🎯 KEY METRICS TO TRACK

**For Each Company:**
```
5-Year Metrics:
├─ Revenue CAGR
├─ Capex CAGR
├─ Debt CAGR
└─ FCF Average

Prediction Accuracy:
├─ Precision (buy accuracy)
├─ Recall (coverage of winners)
├─ F1 Score (overall quality)
└─ Return Spread (alpha generation)

Risk Metrics:
├─ Max Drawdown
├─ Sharpe Ratio
└─ Win Rate (% profitable picks)
```

---

## 🚀 NEXT IMMEDIATE STEPS

### Step 1: Finalize Company List (Next 2 hours)
```bash
# Verify 60 companies are tradeable on yfinance
python3 quarterly_data_collector.py --validate_tickers
```

### Step 2: Collect Quarterly Fundamentals (Tomorrow)
```bash
# Fetch 5 years of quarterly data for 60 companies
python3 quarterly_data_collector.py --collect_all
```

### Step 3: Analyze Quarterly Trends (Tomorrow)
```bash
# Generate trend report
python3 quarterly_data_collector.py --analyze_trends
```

### Step 4: Collect Daily Prices (Next 2 days)
```bash
# Fetch 1,825 trading days × 60 companies
python3 daily_price_collector.py --collect_all
```

### Step 5: Merge & Validate (Next 3 days)
```bash
# Merge quarterly + daily data
python3 data_merger.py --merge
```

### Step 6: Run Backtest (Next 4-5 days)
```bash
# Run MAIN weights backtest
python3 backtest_runner.py --weights main

# Run KARZ weights backtest
python3 backtest_runner.py --weights karz

# Generate comparison
python3 backtest_analyzer.py --compare
```

---

## 📞 QUESTIONS FOR DATA COLLECTION

1. **Data sources:** Should we use yfinance for all data, or include Bloomberg/other sources?
2. **Stock adjustments:** Include dividend-adjusted and split-adjusted prices?
3. **Missing data:** How to handle companies with <5 years of data?
4. **Currencies:** All USD, or include local currencies?
5. **Survivorship bias:** Include delisted companies, or only surviving companies?

---

**Status:** Ready to begin Phase 1 data collection  
**Estimated completion:** 3-4 weeks for full backtest  
**Next action:** Start quarterly data collection tomorrow  

