#!/usr/bin/env python3
"""
Quarterly Data Collection - Phase 1 of Backtest Data Pipeline
==============================================================
Collects 5 years of quarterly financial data for 60 Tier 2 companies.
Analyzes trends before diving into 1,825 days of daily price data.

Strategy:
1. Select 60 representative companies (top, mid, bottom tier performers)
2. Fetch quarterly fundamentals (20 quarters = 5 years)
3. Extract key metrics: debt, capex, CF, revenue, earnings, margins
4. Analyze quarterly trends
5. Prepare for daily price data collection
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')


class QuarterlyDataCollector:
    """Collect 5 years of quarterly financial data from yfinance"""

    def __init__(self, output_dir: str = '/private/tmp/claude-501/-Users-umashankar/7c1286ad-5a8d-41f6-8f3d-6f5a2866ae33/scratchpad/backtest_data'):
        """Initialize collector"""
        self.output_dir = output_dir
        self.collected_data = {}
        self.failed_companies = []

        print(f"\n📊 QUARTERLY DATA COLLECTOR - Phase 1 of Backtest Pipeline")
        print(f"   Output directory: {output_dir}")

    def select_sample_companies(self, n_companies: int = 60) -> List[str]:
        """
        Select 60 representative companies across sectors and market caps.
        Using a mix of real tickers and representative symbols.
        """

        # Mix of large, mid, and small cap companies across sectors
        sample_tickers = [
            # Tech/Cloud (15)
            'MSFT', 'NVDA', 'CRM', 'ADBE', 'AVGO',
            'MSTR', 'FTNT', 'NET', 'DDOG', 'CRWD',
            'PSTG', 'SNOW', 'PANW', 'ORCL', 'ACHR',

            # Industrials/Manufacturing (15)
            'CAT', 'GE', 'LMT', 'BA', 'RTX',
            'ISRG', 'ABB', 'EMR', 'WAFER', 'CARR',
            'TT', 'IRM', 'AAPL', 'FLEX', 'MES',

            # Energy/Materials (12)
            'CVX', 'COP', 'SLB', 'MPC', 'OKE',
            'NUE', 'FCX', 'CF', 'ALB', 'LYB',
            'DOW', 'HUN',

            # Transportation (6)
            'DAL', 'UAL', 'ALK', 'NCLH', 'CCL', 'RCL',

            # Real Estate/Infrastructure (8)
            'PLD', 'DLR', 'EQIX', 'VICI', 'PSA', 'UMC', 'CCI', 'AMT',

            # Healthcare/Pharma (8)
            'JNJ', 'PFE', 'MRK', 'BIIB', 'JAZZ', 'BMY', 'AMGN', 'GILD'
        ]

        print(f"\n🎯 COMPANY SELECTION")
        print(f"   Total companies: {len(sample_tickers[:n_companies])}")
        print(f"   Sectors: Tech, Industrials, Energy, Transportation, Real Estate, Healthcare")
        print(f"   Time period: 5 years (20 quarters)")

        return sample_tickers[:n_companies]

    def fetch_quarterly_data(self, ticker: str, years: int = 5) -> Dict:
        """
        Fetch quarterly financial data from yfinance for last 5 years.
        Extracts: revenue, debt, capex, cash flow, earnings, margins
        """

        try:
            # Fetch company info and quarterly financials
            company = yf.Ticker(ticker)

            # Get quarterly income statement and balance sheet
            quarterly_financials = company.quarterly_financials
            quarterly_balance_sheet = company.quarterly_balance_sheet
            quarterly_cashflow = company.quarterly_cashflow

            if quarterly_financials.empty or quarterly_balance_sheet.empty:
                return None

            # Get last 20 quarters (5 years)
            quarters = []

            for i in range(min(20, len(quarterly_financials.columns))):
                try:
                    quarter_date = quarterly_financials.columns[i]

                    # Extract metrics
                    revenue = quarterly_financials.loc['Total Revenue', quarter_date] if 'Total Revenue' in quarterly_financials.index else 0
                    operating_income = quarterly_financials.loc['Operating Income', quarter_date] if 'Operating Income' in quarterly_financials.index else 0
                    net_income = quarterly_financials.loc['Net Income', quarter_date] if 'Net Income' in quarterly_financials.index else 0

                    # Balance sheet
                    total_debt = 0
                    if 'Short Term Debt' in quarterly_balance_sheet.index:
                        total_debt += quarterly_balance_sheet.loc['Short Term Debt', quarter_date]
                    if 'Long Term Debt' in quarterly_balance_sheet.index:
                        total_debt += quarterly_balance_sheet.loc['Long Term Debt', quarter_date]

                    total_equity = quarterly_balance_sheet.loc['Total Stockholder Equity', quarter_date] if 'Total Stockholder Equity' in quarterly_balance_sheet.index else 1

                    # Cash flow
                    operating_cf = quarterly_cashflow.loc['Operating Cash Flow', quarter_date] if 'Operating Cash Flow' in quarterly_cashflow.index else 0
                    capex = quarterly_cashflow.loc['Capital Expenditure', quarter_date] if 'Capital Expenditure' in quarterly_cashflow.index else 0
                    capex = abs(capex) if capex < 0 else capex  # Capex typically negative

                    # Calculate derived metrics
                    fcf = operating_cf - capex
                    debt_to_equity = total_debt / (total_equity + 0.01) if total_equity > 0 else 0
                    oi_margin = (operating_income / (revenue + 0.01)) * 100 if revenue > 0 else 0
                    ni_margin = (net_income / (revenue + 0.01)) * 100 if revenue > 0 else 0
                    capex_intensity = (capex / (revenue + 0.01)) * 100 if revenue > 0 else 0

                    quarters.append({
                        'quarter_date': quarter_date,
                        'quarter': quarter_date.strftime('%Y-Q%q') if hasattr(quarter_date, 'strftime') else str(quarter_date),
                        'revenue': revenue,
                        'operating_income': operating_income,
                        'net_income': net_income,
                        'operating_cf': operating_cf,
                        'capex': capex,
                        'fcf': fcf,
                        'total_debt': total_debt,
                        'total_equity': total_equity,
                        'debt_to_equity': debt_to_equity,
                        'oi_margin': oi_margin,
                        'ni_margin': ni_margin,
                        'capex_intensity': capex_intensity,
                    })

                except:
                    continue

            if len(quarters) < 10:  # Need at least 2.5 years
                return None

            return {
                'ticker': ticker,
                'company_name': company.info.get('longName', ticker) if hasattr(company, 'info') else ticker,
                'sector': company.info.get('sector', 'Unknown') if hasattr(company, 'info') else 'Unknown',
                'quarters': sorted(quarters, key=lambda x: x['quarter_date'], reverse=True)
            }

        except Exception as e:
            return None

    def collect_all(self, tickers: List[str]) -> pd.DataFrame:
        """Collect data for all tickers"""

        print(f"\n🔄 FETCHING QUARTERLY DATA (5 YEARS = 20 QUARTERS)")
        print(f"   Companies to fetch: {len(tickers)}")

        all_data = []
        success_count = 0

        for i, ticker in enumerate(tickers, 1):
            print(f"   [{i:2d}/{len(tickers)}] {ticker:6s}...", end=' ', flush=True)

            data = self.fetch_quarterly_data(ticker)

            if data and len(data['quarters']) > 0:
                print(f"✅ {len(data['quarters'])} quarters")
                all_data.append(data)
                success_count += 1
            else:
                print(f"❌ Failed")
                self.failed_companies.append(ticker)

        print(f"\n✅ Successfully fetched: {success_count}/{len(tickers)} companies")
        print(f"❌ Failed: {len(self.failed_companies)}")

        return all_data

    def analyze_trends(self, data: List[Dict]) -> pd.DataFrame:
        """Analyze quarterly trends for each company"""

        print(f"\n" + "="*80)
        print(f"QUARTERLY TREND ANALYSIS (5-YEAR OVERVIEW)")
        print(f"="*80)

        trends = []

        for company_data in data:
            ticker = company_data['ticker']
            quarters = company_data['quarters']

            if len(quarters) < 8:  # Need at least 2 years
                continue

            # Calculate 5-year trends (all quarters)
            revenues = [q['revenue'] for q in quarters]
            capex_list = [q['capex'] for q in quarters]
            debt_list = [q['total_debt'] for q in quarters]
            fcf_list = [q['fcf'] for q in quarters]
            oi_margins = [q['oi_margin'] for q in quarters]

            # Average and growth
            avg_revenue = np.mean(revenues)
            avg_capex = np.mean(capex_list)
            avg_fcf = np.mean(fcf_list)

            # Growth rates (compare oldest to newest quarters)
            if len(revenues) > 4:
                revenue_cagr = ((revenues[0] / revenues[-1]) ** (1/5) - 1) * 100 if revenues[-1] > 0 else 0
                capex_cagr = ((capex_list[0] / capex_list[-1]) ** (1/5) - 1) * 100 if capex_list[-1] > 0 else 0
                debt_cagr = ((debt_list[0] / debt_list[-1]) ** (1/5) - 1) * 100 if debt_list[-1] > 0 else 0
            else:
                revenue_cagr = capex_cagr = debt_cagr = 0

            # Margin trends
            avg_oi_margin = np.mean(oi_margins)
            margin_trend = oi_margins[0] - oi_margins[-1] if len(oi_margins) > 1 else 0

            # Expansion profile
            is_expanding = capex_cagr > 5 and avg_capex > avg_revenue * 0.05
            is_deleveraging = debt_cagr < 0 or avg_fcf > avg_capex
            expanding_with_debt = capex_cagr > 5 and debt_cagr > 5

            trends.append({
                'ticker': ticker,
                'company_name': company_data['company_name'],
                'sector': company_data['sector'],
                'n_quarters': len(quarters),
                'avg_revenue': avg_revenue,
                'avg_capex': avg_capex,
                'avg_fcf': avg_fcf,
                'revenue_cagr_pct': revenue_cagr,
                'capex_cagr_pct': capex_cagr,
                'debt_cagr_pct': debt_cagr,
                'avg_oi_margin': avg_oi_margin,
                'margin_trend_pp': margin_trend,
                'is_expanding': is_expanding,
                'is_deleveraging': is_deleveraging,
                'expanding_with_debt': expanding_with_debt,
            })

        trends_df = pd.DataFrame(trends)

        # Print analysis
        print(f"\n📊 EXPANSION PROFILE SUMMARY")
        print(f"   Aggressive expanders (high capex + debt growth): {trends_df['expanding_with_debt'].sum():,}")
        print(f"   Conservative expanders (capex growth + deleveraging): {(trends_df['is_expanding'] & trends_df['is_deleveraging']).sum():,}")
        print(f"   Stable operators: {(~trends_df['is_expanding']).sum():,}")

        # Top expanders by capex CAGR
        print(f"\n🚀 TOP CAPEX GROWERS (5-Year CAGR)")
        top_capex = trends_df.nlargest(5, 'capex_cagr_pct')
        for idx, row in top_capex.iterrows():
            print(f"   {row['ticker']:8s} | {row['company_name'][:30]:30s} | Capex CAGR: {row['capex_cagr_pct']:+6.1f}%")

        # Deleveraging players
        print(f"\n📉 TOP DELEVERAGING PLAYERS (5-Year Debt CAGR)")
        top_deleverage = trends_df.nsmallest(5, 'debt_cagr_pct')
        for idx, row in top_deleverage.iterrows():
            print(f"   {row['ticker']:8s} | {row['company_name'][:30]:30s} | Debt CAGR: {row['debt_cagr_pct']:+6.1f}%")

        # Margin expanders
        print(f"\n📈 MARGIN EXPANSION PLAYS (Improving OI Margin)")
        margin_exp = trends_df.nlargest(5, 'margin_trend_pp')
        for idx, row in margin_exp.iterrows():
            print(f"   {row['ticker']:8s} | {row['company_name'][:30]:30s} | Margin change: {row['margin_trend_pp']:+6.1f}pp")

        return trends_df

    def generate_daily_price_plan(self, trends_df: pd.DataFrame) -> Dict:
        """Generate plan for daily price data collection"""

        print(f"\n" + "="*80)
        print(f"PHASE 2 READINESS: DAILY PRICE DATA COLLECTION")
        print(f"="*80)

        n_companies = len(trends_df)
        n_days = 365 * 5
        total_data_points = n_companies * n_days

        print(f"\n📊 DATA SCALE FOR PHASE 2")
        print(f"   Companies: {n_companies}")
        print(f"   Time period: 5 years = {n_days} trading days")
        print(f"   Total data points: {total_data_points:,} price points")
        print(f"   Plus metrics: {total_data_points * 8:,} metric values")

        print(f"\n🔄 DAILY DATA COLLECTION STRATEGY")
        print(f"   1. Fetch daily close prices for each company (5 years)")
        print(f"   2. Calculate daily returns")
        print(f"   3. Merge with quarterly fundamentals")
        print(f"   4. Create rolling 1-year return windows")
        print(f"   5. Match actual returns to quarterly metrics")
        print(f"   6. Run backtest analysis")

        print(f"\n⏱️  ESTIMATED TIME & STORAGE")
        print(f"   Fetch time: ~30-60 minutes (yfinance rate limits)")
        print(f"   Storage: ~100-150 MB (all 5 years, 60 companies)")
        print(f"   Processing: ~5-10 minutes for backtest")

        return {
            'n_companies': n_companies,
            'n_days': n_days,
            'total_points': total_data_points,
            'estimated_fetch_time_min': 45,
            'estimated_storage_mb': 125,
        }

    def export_results(self, trends_df: pd.DataFrame, filepath: str) -> None:
        """Export quarterly trends to CSV"""

        trends_df.to_csv(filepath, index=False)
        print(f"\n✅ Quarterly trends exported to {filepath}")

        # Also export company list for next phase
        company_list = trends_df[['ticker', 'company_name', 'sector']].copy()
        company_list.to_csv(filepath.replace('trends', 'companies'), index=False)
        print(f"✅ Company list exported for Phase 2")


if __name__ == "__main__":
    print("\n" + "📊 "*40)
    print("QUARTERLY DATA COLLECTION - Phase 1: Trend Analysis Before Daily Data")
    print("📊 "*40)
