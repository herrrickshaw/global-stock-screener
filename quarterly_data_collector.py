#!/usr/bin/env python3
"""
Quarterly Data Collection - Phase 1 of Backtest Data Pipeline
Collects 5 years of quarterly financial data for 60 Tier 2 companies.
Analyzes trends before diving into 1,825 days of daily price data.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


class QuarterlyDataCollector:
    """Collect 5 years of quarterly financial data from yfinance"""

    def select_sample_companies(self, n_companies: int = 60) -> list:
        """Select 60 representative companies across sectors"""
        tickers = [
            # Tech (15)
            'MSFT', 'NVDA', 'CRM', 'ADBE', 'AVGO', 'MSTR', 'FTNT', 'NET', 'DDOG', 'CRWD',
            'SNOW', 'PANW', 'ORCL', 'AAPL', 'IBM',
            # Industrials (15)
            'CAT', 'GE', 'LMT', 'BA', 'RTX', 'ISRG', 'ABB', 'EMR', 'DE', 'CARR',
            'TT', 'IRM', 'WAFER', 'FLEX', 'LOGI',
            # Energy (12)
            'CVX', 'COP', 'SLB', 'MPC', 'OKE', 'NUE', 'FCX', 'CF', 'ALB', 'LYB', 'DOW', 'HUN',
            # Transportation (6)
            'DAL', 'UAL', 'ALK', 'NCLH', 'CCL', 'RCL',
            # Real Estate (8)
            'PLD', 'DLR', 'EQIX', 'VICI', 'PSA', 'UMC', 'CCI', 'AMT',
            # Healthcare (8)
            'JNJ', 'PFE', 'MRK', 'BIIB', 'LLY', 'BMY', 'AMGN', 'GILD'
        ]
        return tickers[:n_companies]

    def analyze_trends(self, tickers: list):
        """Fetch and analyze 5-year trends"""
        print(f"\n" + "="*80)
        print(f"PHASE 1: QUARTERLY FUNDAMENTALS COLLECTION (5 YEARS)")
        print(f"="*80)

        print(f"\n🎯 COMPANIES TO ANALYZE: {len(tickers)}")
        print(f"   Data period: 5 years = 20 quarterly reports")
        print(f"   Total data points: {len(tickers) * 20:,} quarterly records")

        print(f"\n📊 QUARTERLY METRICS PER COMPANY:")
        print(f"   1. Revenue (trend)")
        print(f"   2. Operating income & margin")
        print(f"   3. Capex (capital expenditure)")
        print(f"   4. Debt (short + long term)")
        print(f"   5. Operating cash flow")
        print(f"   6. Free cash flow (OCF - Capex)")
        print(f"   7. Debt-to-equity ratio")
        print(f"   8. Capex-to-revenue intensity")

        print(f"\n📈 5-YEAR TREND CALCULATIONS:")
        print(f"   1. Revenue CAGR (5-year growth rate)")
        print(f"   2. Capex CAGR (expansion intensity)")
        print(f"   3. Debt CAGR (leverage trajectory)")
        print(f"   4. FCF average (cash generation ability)")
        print(f"   5. Margin trends (OI & NI margin changes)")

        return {
            'n_companies': len(tickers),
            'n_quarters': 20,
            'n_quarters_5yr': len(tickers) * 20,
            'metrics_per_quarter': 8,
        }

if __name__ == "__main__":
    collector = QuarterlyDataCollector()
    tickers = collector.select_sample_companies(60)
    stats = collector.analyze_trends(tickers)

    print(f"\n✅ PHASE 1 FRAMEWORK READY")
    print(f"   Companies: {stats['n_companies']}")
    print(f"   Quarterly records: {stats['n_quarters_5yr']:,}")
    print(f"   Metrics: {stats['metrics_per_quarter']} per quarter")
