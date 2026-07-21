#!/usr/bin/env python3
"""
screener_history_collector.py — collect POINT-IN-TIME historical ANNUAL financials
for INDIAN (NSE/BSE) tickers from screener.in's per-company Excel export, so the
fundamental screeners (Piotroski, Coffee Can) can be BACKTESTED on India without
look-ahead — the India analogue of sec_history_collector.py (which does US via
SEC EDGAR).

Each company's screener.in export carries a "Data Sheet" with ANNUAL line items
aligned to a fiscal "Report Date" axis (Mar-YYYY, ~10 years). We extract the
Piotroski/Coffee-Can inputs per fiscal year:
  net_income, revenue, cfo, borrowings, reserves, equity_capital, other_liab,
  inventory, receivables, cash, operating_profit, shares, dividend_amount.

Also attaches, per fiscal year (2026-07-18, no-lookahead as-of merge from the
company page's Shareholding Pattern table -- see industry_and_shareholding_of()
and screener_in_auth.parse_shareholding_dated()):
  promoter_holding, fii_holding, dii_holding, public_holding, num_shareholders
Coverage is bounded by what screener.in's page renders (~3 trailing years) --
fy_ends older than that have no match and stay unset, not fabricated.

CAVEAT vs the US collector: screener.in exposes the fiscal PERIOD-END but NOT the
filing date. Indian issuers must file audited annual results within ~60 days of the
FY-end (SEBI LODR); the backtest therefore enters `fy_end + reporting-lag` days
later (default 90) as a conservative, no-look-ahead proxy — there is no earlier
as-of date available, so this is the honest best we can do.

Output: cache_seed/fundamentals_history/IN.parquet — long format, one row per
(ticker, fy_end). Resumable: reuses already-collected tickers on re-run.

  python3 screener_history_collector.py                 # NSE universe (data/global_universe/IN.csv)
  python3 screener_history_collector.py --limit 200      # test on the first 200
  python3 screener_history_collector.py --tickers RELIANCE TCS INFY
  python3 screener_history_collector.py --liquid-only     # only names present in cache_seed/ltm/IN.parquet
"""
import argparse
import io
import os
import re
import time

import pandas as pd

# BASE used to hardcode ~/Downloads/code/python_files. That tree was migrated away
# from AND is periodically mass-wiped by a parallel session, so all three derived
# paths (UNIVERSE, LTM, OUT_DIR) resolved to nothing — and OUT_DIR pointing there
# meant a 30-minute collection would write straight into the wipe zone.
# Resolve against this file's own repo, which is where cache_seed/ltm/IN.parquet
# actually lives; fall back to the legacy path only if it still exists.
_HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY = os.path.expanduser("~/Downloads/code/python_files")
BASE = _HERE if os.path.exists(os.path.join(_HERE, "cache_seed")) else _LEGACY
OUT_DIR = os.environ.get("FUND_HIST_DIR") or os.path.join(
    BASE, "cache_seed", "fundamentals_history"
)
OUT = os.path.join(OUT_DIR, "IN.parquet")
UNIVERSE = os.path.join(BASE, "data", "global_universe", "IN.csv")
LTM = os.path.join(BASE, "cache_seed", "ltm", "IN.parquet")
_RATE = 0.7  # polite delay between screener.in fetches (ToS-friendly)
# Consecutive empty fetches before aborting. A real universe has gaps (BSE-only names
# 404 on the NSE-shaped URL), but ~30 in a row is a block, not a coincidence.
MAX_CONSECUTIVE_EMPTY = 30
# 2026-07-18: TIME-based checkpoint floor, alongside the existing every-100-
# tickers count trigger below -- whichever fires first. The count trigger
# alone bounds data loss to "100 tickers" but not to a fixed WALL-CLOCK
# amount; a slow stretch (heavy per-ticker latency, retries) could go well
# past 10 minutes between count-triggered checkpoints. This bounds worst-
# case loss on a crash/kill to one interval regardless of throughput.
_CHECKPOINT_INTERVAL_SEC = 600

# Data-Sheet row label → our field name (annual series only; first present wins).
FIELDS = {
    "net_income": ["Net profit", "Net Profit"],
    "revenue": ["Sales", "Sales+", "Revenue", "Total Revenue"],
    # "Operating Profit" is DELIBERATELY NOT mapped, despite existing in the export.
    # It appears ONLY inside the "Quarters" block (row ~49), whose Report-Date axis
    # carries Jun/Sep/Dec and is correctly rejected by _is_annual_axis. screener.in
    # does not publish an annual Operating Profit row at all: the "PROFIT & LOSS"
    # block runs Sales -> ... -> Interest -> Profit before tax -> Net profit with no
    # operating-profit line. Mapping the label would silently splice a QUARTERLY
    # figure into an annual series — a far worse bug than the missing column, because
    # it would look populated and be wrong by ~4x.
    #
    # EBIT is instead DERIVED from two directly-reported ANNUAL line items:
    #     EBIT = profit_before_tax + interest
    # which is the textbook definition ROCE takes as its numerator. This is addition
    # of reported figures, NOT the ratio-inversion trap (equity = net_income/roe)
    # that previously produced absurd ROCE of 95-137%.
    "profit_before_tax": ["Profit before tax", "Profit Before Tax", "PBT"],
    "interest": ["Interest", "Interest Expense", "Finance Costs"],
    # COGS components. screener.in has no "Gross Profit" or "COGS" row — it itemises
    # the cost lines — so gross profit is built from them (see collect_ticker).
    "raw_material_cost": ["Raw Material Cost"],
    "change_in_inventory": ["Change in Inventory"],
    "power_and_fuel": ["Power and Fuel"],
    "other_mfr_exp": ["Other Mfr. Exp", "Other Mfr Exp"],
    "cfo": ["Cash from Operating Activity", "Cash from Operating Activity+"],
    # TOTAL ASSETS. screener.in labels this row just "Total" — it appears TWICE
    # in the BALANCE SHEET block: row 60 closes liabilities+equity, row 65 closes
    # assets. Verified 2026-07-21 on RELIANCE and TCS: the two rows are
    # bit-identical across all 10 fiscal years (max abs diff 0), as the accounting
    # identity requires, so first-match is safe and `seen` taking row 60 is fine.
    #
    # This row was NEVER mapped, which is why total_assets was 0% on every
    # screener-sourced row. Five of nine Piotroski tests use it as a denominator
    # (F1, F3, F4, F9) and two more need the balance sheet (F5, F6), so f_tested
    # capped at 3 and the India panel reported piotroski=0 for 3,405 firm-years —
    # a missing field reading as "the factor never fires".
    "total_assets": ["Total"],
    "borrowings": ["Borrowings", "Borrowings+", "Total Debt"],
    "reserves": ["Reserves"],
    "equity_capital": ["Equity Capital", "Equity Share Capital", "Share Capital"],
    "other_liab": ["Other Liabilities", "Other Liabilities+"],
    "inventory": ["Inventory", "Inventories"],
    "receivables": ["Trade receivables", "Debtors", "Receivables"],
    "cash": ["Cash & Bank", "Cash Equivalents"],
    "shares": ["No. of Equity Shares", "No of Equity Shares"],
    # 2026-07-18: ported from company_financials() in screener_in_auth.py,
    # which already extracts this exact row from the same Data Sheet via an
    # identical row() lookup -- that function's "dividend_history"/
    # "dividend_pay_years" outputs were never wired into THIS collector's
    # FIELDS/_extract_annual path, so the annual point-in-time panel this
    # file builds has been silently missing dividends despite the sister
    # function already parsing them from the same downloaded workbook.
    "dividend_amount": ["Dividend Amount", "Dividend Paid", "Dividend Payout"],
}


def _zero(x):
    """NaN/None -> 0.0. `(x or 0)` cannot do this: NaN is TRUTHY, so `nan or 0` is nan."""
    return 0.0 if x is None or x != x else float(x)


# ── non-equity instruments ────────────────────────────────────────────────────
# The GSS price panel is 23% NON-EQUITY: 1,984 coupon-prefixed bonds (1010EFSL29,
# 805HDFCB29), 141 G-secs/SDLs (1018GS2026), 169 T-bills. Median 90 shares/day against
# 76,887 for real equities.
#
# A VALUE-based liquidity floor does NOT remove them — that is the whole trap. A bond
# trading 90 units/day at Rs 1 lakh face value turns over Rs 90 lakh and sails through a
# Rs 1 crore gate. This is the LIQUIDSBI incident (an ETF shipped as a golden-cross pick)
# at 2,593x scale, and it is why the India collection wasted fetches on bonds screener.in
# will never serve.
#
# Structure, not value, is the discriminator — the same lesson as the ISIN prefix
# (INE=equity, INF=fund, IN0-3=G-Sec).
_BOND = re.compile(r"^\d{3,4}[A-Z]+\d{2,4}$")  # coupon + issuer + maturity year
_GSEC = re.compile(r"GS\d{4}$|^SDL|SDL\d|GOI")
_TBIL = re.compile(r"^(91D|182D|364D)|TB\d{2}")


def is_non_equity(sym: str) -> bool:
    r"""True for bonds / G-secs / T-bills masquerading as equities.

    The trailing-digits requirement in _BOND matters: `^\d{3,4}[A-Z]` alone flags 360ONE
    (360 + ONE), a real equity. Real bonds carry a maturity year — 1010EFSL29 -> 1010,
    EFSL, 29. Verified: this pattern keeps 360ONE and drops 1010EFSL29.
    """
    s = (sym or "").strip().upper()
    return bool(_BOND.match(s) or _GSEC.search(s) or _TBIL.search(s))


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _is_annual_axis(vals):
    """A 'Report Date' row is the ANNUAL axis iff every date is a fiscal year-end
    (month == 3). Quarterly Report-Date rows carry Jun/Sep/Dec and are skipped so we
    never mistake a quarterly Sales/Net-profit row for the annual one."""
    dates = [v for v in vals if isinstance(v, pd.Timestamp) or hasattr(v, "month")]
    if not dates:
        return None
    if all(getattr(d, "month", 0) == 3 for d in dates):
        return [pd.Timestamp(d).normalize() for d in dates]
    return None


# ── lender detection: the SECTOR FIELD, from the company page ─────────────────
# THREE RATIO/STRUCTURE DETECTORS WERE REFUTED BEFORE THIS ONE, and the reason matters:
#   1. interest/revenue >= 25%  -> caught ADANIPOWER (a POWER utility), missed 360ONE.
#                                  Measures LEVERAGE, not LENDING.
#   2. EBIT margin, any cut     -> lenders -24.6%..+95.8%, non-lenders +7.7%..+902.8%.
#                                  TOTAL OVERLAP. Ratios are the OUTPUT of a business
#                                  model; they cannot reveal it.
#   3. "Financing Profit" rows  -> HDFCBANK detected as NOT-lender. screener.in
#                                  NORMALISES every company into one Data Sheet template:
#                                  HDFCBANK shows Sales 69,305.96 (interest income written
#                                  into the Sales line), Raw Material Cost nan, Interest
#                                  36,166.73 (52% of Sales). The EXPORT has no sector signal.
#
# The company PAGE does. It carries an Industry field the export omits:
#     HDFCBANK   Banks               IN05      AADHARHFC  Finance          IN05
#     360ONE     Capital Markets     IN05      5PAISA     Capital Markets  IN05
#     ADANIPOWER Power               IN11      TCS        IT - Software    IN08
#     3MINDIA    Diversified         IN12      APCOTEXIND Industrial Prod. IN07
# Verified against the exact cases that broke all three earlier detectors: every lender
# is IN05, every industrial is not.
#
# ⚠️ 3PLAND classifies as Finance/IN05 and I had labelled it "not-lender" from its name
# (3P LAND -> real estate). The classifier is right and my label was wrong — its interest
# is 908% of revenue. Sector comes from the source, not from reading tickers.
#
# WHY IT IS WORTH ONE EXTRA FETCH PER TICKER (~+28 min on 2,367 names): for a bank/NBFC
# `ebit = pbt + interest` adds back their cost of goods sold. EBIT inflates ~4x,
# borrowings inflate capital_employed ~9x, and THE ERRORS PARTIALLY CANCEL — AADHARHFC
# lands at ROCE 8.5-10.7% every year, INSIDE the 5-25% plausibility band, so no range
# check can ever fire. True ROE is 14.1-16.8%. 34/245 rows flip a live screen threshold.
# An undetectable wrong number is worth 28 minutes to remove.
_FINANCIAL_INDUSTRIES = (
    "bank",
    "finance",
    "financial",
    "capital market",
    "nbfc",
    "insurance",
    "asset management",
    "housing finance",
    "investment",
)
_INDUSTRY_RE = None


def industry_of(sess_mod, ticker):
    """Industry string from screener.in's company page, or None. One extra GET."""
    global _INDUSTRY_RE
    import re

    if _INDUSTRY_RE is None:
        _INDUSTRY_RE = re.compile(r"Industry[^<]*</[^>]+>\s*<[^>]+>([^<]{2,40})<", re.I)
    try:
        s = sess_mod.session()
        h = s.get(f"https://www.screener.in/company/{ticker}/", timeout=25).text
    except Exception:
        return None
    m = _INDUSTRY_RE.search(h)
    return m.group(1).strip() if m else None


def industry_and_shareholding_of(sess_mod, ticker):
    """Industry string + quarterly shareholding records from ONE company-page
    GET (2026-07-18) -- industry_of() and a naive shareholding fetch would
    each independently re-GET the same page, doubling an already-extra
    fetch per ticker. Reuses sess_mod.parse_shareholding_dated() (added
    alongside the live-path _parse_shareholding() in screener_in_auth.py)
    so both consumers share one regex-parsing implementation."""
    global _INDUSTRY_RE
    if _INDUSTRY_RE is None:
        _INDUSTRY_RE = re.compile(r"Industry[^<]*</[^>]+>\s*<[^>]+>([^<]{2,40})<", re.I)
    try:
        s = sess_mod.session()
        h = s.get(f"https://www.screener.in/company/{ticker}/", timeout=25).text
    except Exception:
        return None, []
    m = _INDUSTRY_RE.search(h)
    industry = m.group(1).strip() if m else None
    try:
        shareholding = sess_mod.parse_shareholding_dated(h)
    except Exception:
        shareholding = []
    return industry, shareholding


def is_financial(industry) -> bool:
    """True when the SOURCE classifies this as a lender/financial.

    Returns False on None: an unknown industry is not evidence of being industrial, but
    declining every un-fetched company would empty the dataset. Callers get `industry`
    on the row and can filter harder.
    """
    if not industry:
        return False
    i = industry.strip().lower()
    return any(k in i for k in _FINANCIAL_INDUSTRIES)


def _extract_annual(df):
    """Walk the Data Sheet top→bottom, tracking the current annual Report-Date axis,
    and pull each wanted field's values aligned to fiscal year-ends. Returns
    {fy_end: {field: value}}. First annual occurrence of a field wins (the annual
    block precedes the quarterly block for Sales/Net profit)."""
    # invert label → field for quick lookup
    label_to_field = {}
    for field, labels in FIELDS.items():
        for lab in labels:
            label_to_field[lab.strip().lower()] = field

    axis = None  # current annual fiscal axis (list of Timestamps) or None if quarterly
    out = {}  # fy_end -> {field: val}
    seen = set()  # fields already captured (first annual wins)
    for _, r in df.iterrows():
        cells = r.tolist()
        label = str(cells[0]).strip().lower()
        vals = cells[1:]
        if label == "report date":
            axis = _is_annual_axis(vals)
            continue
        if axis is None:
            continue
        field = label_to_field.get(label)
        if field is None or field in seen:
            continue
        seen.add(field)
        for dt, v in zip(axis, vals):
            n = _num(v)
            if n is not None:
                out.setdefault(pd.Timestamp(dt), {})[field] = n
    return out


class Blocked(RuntimeError):
    """screener.in stopped serving us. Raised so the caller can ABORT, not grind on."""


def collect_ticker(sess_mod, ticker):
    """Fetch + parse one company. Returns list of per-fiscal-year row dicts.

    Raises Blocked when the host refuses the connection, so main() can stop.
    Previously every failure was swallowed into `return []`, which turned a block into a
    silent no-op: on 2026-07-15 a run was blocked ~1 MINUTE in, then spent 40 MINUTES
    walking 2,367 tickers whose every fetch failed, and reported "2367/2367 | 31 with
    data" — a completion message for a job that collected nothing after the first
    minute. A failure that looks like progress is worse than a crash.
    """
    try:
        raw = sess_mod.company_export_bytes(ticker)
    except Exception as e:
        if "Max retries" in str(e) or "Connection" in type(e).__name__:
            raise Blocked(f"host refused connection at {ticker}: {str(e)[:60]}") from e
        return []
    if not raw:
        return []
    try:
        xl = pd.ExcelFile(io.BytesIO(raw))
        sheet = next((s for s in xl.sheet_names if "data" in s.lower()), xl.sheet_names[0])
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet, header=None)
    except Exception:
        return []
    annual = _extract_annual(df)
    # 2026-07-18: BUG FOUND IN PRODUCTION. This page fetch used to fire
    # immediately after the export fetch above with ZERO delay between them
    # -- only the outer _RATE sleep in main()'s loop applies BETWEEN
    # tickers' first request, not between a single ticker's two requests.
    # A live bulk run measured this: industry (and therefore shareholding,
    # parsed from the same response) succeeded for only ~5% of 1,735
    # tickers, while the export-sourced fields (revenue, net_income, ...)
    # were populated normally -- and the SAME fetch succeeded instantly
    # (1.5s) when tested standalone/isolated, ruling out a broken endpoint
    # or a real block. This is rate-throttling triggered by the back-to-
    # back request pattern specifically, not overall request volume (the
    # export fetch right before it was fine). One retry with backoff,
    # mirroring the proven pattern main() already uses for collect_ticker()
    # itself as a whole.
    time.sleep(_RATE)
    industry, shareholding = industry_and_shareholding_of(sess_mod, ticker)
    if industry is None and not shareholding:
        time.sleep(_RATE * 2)
        industry, shareholding = industry_and_shareholding_of(sess_mod, ticker)
    lender = is_financial(industry)
    rows = []
    for fy, fields in sorted(annual.items()):
        row = {"ticker": ticker, "fy_end": fy.strftime("%Y-%m-%d")}
        row.update(fields)
        # As-of shareholding merge (2026-07-18): screener.in gives no filing
        # date at this stage (see module docstring -- `filed` is computed
        # downstream in merge_india_fundamentals.py from fy_end + reporting
        # lag). Reuse that SAME documented default (90 days) here, locally,
        # purely to pick the latest shareholding quarter that was actually
        # knowable as of this filing -- never a future quarter relative to
        # it. `shareholding` only covers screener.in's trailing ~3-year
        # window (see parse_shareholding_dated()'s docstring): fy_ends
        # further back than that from TODAY have no match and stay
        # unset/NaN, which is correct, not a bug -- there is no page to
        # fetch that would answer for periods that old.
        implied_filed = fy + pd.Timedelta(days=90)
        candidates = [s for s in shareholding if s["quarter_end"] <= implied_filed.date()]
        if candidates:
            best = max(candidates, key=lambda s: s["quarter_end"])
            for k in ("promoter_holding", "fii_holding", "dii_holding",
                      "public_holding", "num_shareholders"):
                if k in best:
                    row[k] = best[k]
        # EBIT and capital employed, derived from reported annual line items so
        # downstream ROCE consumers never re-derive them inconsistently.
        pbt, interest = row.get("profit_before_tax"), row.get("interest")
        rev = row.get("revenue")
        # 🔴 EBIT IS NOT DEFINED FOR LENDERS, AND THIS FILE CANNOT RELIABLY DETECT THEM.
        # `pbt + interest` adds interest back as a financing cost. For a bank/HFC/NBFC
        # interest IS cost of goods sold — borrowing is the raw material. EBIT inflates
        # ~4x, borrowings inflate capital_employed ~9x, AND THE ERRORS PARTIALLY CANCEL:
        # AADHARHFC lands at ROCE 8.5-10.7% every year, INSIDE the 5-25% plausibility
        # band, so no range check can fire. True ROE is 14.1-16.8% — a systematic ~5pp
        # understatement reading as a mediocre business. 34/245 rows flip a live screen
        # threshold. It survived the validation that was run because RELIANCE 8.9% /
        # TCS 56.8% are both NON-financials.
        #
        # An interest/revenue >= 25% gate was tried and REFUTED by the data:
        #     AADHARHFC  48.8%  lender      caught
        #     ADANIPOWER 41.1%  POWER co    FALSE POSITIVE — would void a valid ROCE
        #     360ONE     14.1%  NBFC        FALSE NEGATIVE — missed
        #     5PAISA      9.6%  broker      FALSE NEGATIVE — missed
        # interest/revenue measures LEVERAGE, not LENDING. A heuristic wrong in both
        # directions is worse than none: it would silently void Adani Power while still
        # passing the NBFC the validator flagged.
        #
        # So: FLAG, do not silently decide. `interest_share_of_revenue` is emitted for
        # every row and consumers MUST exclude financials themselves using a real sector
        # source (screener.in renders a different P&L for banks — "Financing Profit" /
        # "Financing Margin" instead of Operating Profit — which is the honest detector,
        # but this collector does not read those rows yet).
        # Until then ROCE for lenders is WRONG and there is no guard. Documented rather
        # than papered over.
        if interest is not None and rev not in (None, 0):
            row["interest_share_of_revenue"] = abs(interest) / abs(rev)
        row["industry"] = industry
        row["is_financial"] = lender
        # DECLINE for financials. A null is honest; ROCE 9.6% for an HFC is not, and it
        # is invisible to every guard the pipeline has.
        if pbt is not None and interest is not None and not lender:
            row["ebit"] = pbt + interest
        # Gross profit. screener.in publishes no Gross Profit / COGS row, so COGS is
        # assembled from the itemised annual cost lines. The sign convention is NOT
        # guessed — it is pinned by reconstructing reported Profit-before-tax:
        #   Sales - RawMat + ChgInv - Power - OtherMfr - Employee - Selling - OtherExp
        #         + OtherIncome - Depreciation - Interest  ==  PBT
        # On RELIANCE FY2017 that reproduces the reported PBT of 40,777 EXACTLY, and
        # only when Change in Inventory is ADDED — it is a credit to profit, hence a
        # REDUCTION of cost. The same chain independently reproduces EBIT 43,500,
        # matching pbt+interest above, so the two derivations corroborate each other.
        #
        # Employee Cost and Selling/admin are EXCLUDED: they are SG&A. Folding them in
        # would compute an OPERATING margin and label it a gross margin — which is the
        # kind of plausible-but-wrong field that is worse than a missing one.
        # GATED ON BUSINESS MODEL — this COGS definition is MANUFACTURER-ONLY.
        #
        # I previously claimed the PBT identity proved gross margin "isn't a judgement
        # call". That was wrong. The identity pins the ARITHMETIC (it proved Change in
        # Inventory is a credit, reproducing reported PBT to the rupee) but says nothing
        # about WHICH lines are cost-of-goods for a given business. TCS exposed it:
        #     Raw Material Cost 94  vs  Sales 92,693  (0.1%)  — because TCS's real cost
        #     of service is Employee Cost 48,116.
        # Formula A would report ~98% gross margin for TCS against a true ~42%, i.e. a
        # plausible-looking, badly wrong number for every IT/services firm in the universe.
        #
        # Validated against yfinance's TRUE Gross Profit (64 company-years, 17 tickers):
        #     rm/sales >30% (manufacturers)  error  -0.1pp   <- essentially exact
        #     rm/sales 5-30% (mixed)         error  +6.7pp
        #     rm/sales <5%  (services)       NO DATA to validate against
        #
        # So the formula is applied ONLY where it was proven, and SKIPPED elsewhere.
        # Skipping is not a cop-out: weigh() drops a None test from both numerator and
        # denominator, so a services firm scores on 7 tests and stays comparable. A
        # wrong-but-populated field is the failure mode this repo keeps hitting (the
        # quarterly Operating Profit splice, the ratio-inverted ROCE at 95-137%, the
        # current-ratio proxy at 62.1% vs a 57.6% coin flip).
        #
        # A services COGS (employee cost as cost of revenue) is defensible in principle
        # but screener.in does not split Employee Cost into direct vs SG&A, and there is
        # no validation sample here for it. Left unimplemented rather than guessed.
        MFR_RM_SHARE_MIN = 0.30
        rm, chg = row.get("raw_material_cost"), row.get("change_in_inventory")
        pf, omf = row.get("power_and_fuel"), row.get("other_mfr_exp")
        sales = row.get("revenue")
        if rm is not None and sales:
            row["rm_share"] = rm / sales
            if row["rm_share"] >= MFR_RM_SHARE_MIN:
                # `(x or 0)` LOOKS safe and is not: _num(np.nan) returns nan, because
                # float(str(nan)) SUCCEEDS so the None fallback never fires — and then
                # `nan or 0` yields nan, because NaN is TRUTHY. That silently voided 15%
                # of gate-passing rows and hit FY2026 for six tickers: the most recent
                # year, the most damaged.
                cogs = rm - _zero(chg) + _zero(pf) + _zero(omf)
                row["cogs"] = cogs
                row["gross_profit"] = sales - cogs
                row["gross_margin"] = row["gross_profit"] / sales
            # else: not a manufacturer -> gross_margin stays absent, test 8 is skipped
        # Capital employed = shareholders' funds + debt. screener.in's balance
        # sheet gives the pieces directly (Equity Share Capital + Reserves +
        # Borrowings), so this is a sum of reported figures, not an inversion.
        eq, res, bor = (row.get("equity_capital"), row.get("reserves"), row.get("borrowings"))
        if eq is not None and res is not None and bor is not None:
            ce = eq + res + bor
            # A NEGATIVE-NET-WORTH shell rescued into positive CE by borrowings is worse
            # than a negative denominator: the `ce > 0` guard fires on ZERO rows and the
            # ratio looks computable. 505196 has net worth -292.07 and CE +118.62, printing
            # +109.4% ROCE off a restructuring write-back. Require positive SHAREHOLDER
            # FUNDS, not just positive CE.
            row["capital_employed"] = ce if (eq + res) > 0 and ce > 0 else None
        # roce only where EBIT is defined — i.e. never for lenders
        if row.get("ebit") is not None and row.get("capital_employed"):
            row["roce"] = row["ebit"] / row["capital_employed"]
        rows.append(row)
    return rows


def _universe(args):
    if args.tickers:
        return [t.upper() for t in args.tickers]
    if os.path.exists(UNIVERSE):
        uni = pd.read_csv(UNIVERSE)
        syms = sorted(
            set(uni["yf_ticker"].astype(str).str.replace(r"\.(NS|BO)$", "", regex=True).str.upper())
        )
        if args.liquid_only and os.path.exists(LTM):
            liq = set(pd.read_parquet(LTM, columns=["Symbol"])["Symbol"].astype(str).str.upper())
            syms = [s for s in syms if s in liq]
        return syms
    # The universe CSV is a build artifact and is often absent. The LTM price
    # parquet is the better source anyway: it IS the traded universe, and
    # --liquid-only only ever intersected against it. Crashing on a missing
    # artifact when the authoritative list is right there is pointless.
    if not os.path.exists(LTM):
        raise SystemExit(f"no universe: neither {UNIVERSE} nor {LTM} exists")
    px = pd.read_parquet(LTM, columns=["Symbol", "Close", "Volume", "Date"])
    if not args.liquid_only:
        return sorted(set(px["Symbol"].astype(str).str.upper()))
    # --liquid-only MUST still filter here. The first cut of this fallback ignored
    # the flag and returned all 8,944 symbols in the LTM parquet, turning a ~28-minute
    # job into a ~3.5-HOUR one against a rate-limited host — and silently, because the
    # count is only printed once. The flag exists precisely to avoid hammering
    # screener.in for names too illiquid to trade.
    #
    # Liquidity is the same gate used everywhere else in this repo: MEDIAN daily
    # turnover >= Rs 1 crore, median so one block deal cannot lift a dead stock over
    # the bar. Applied on the last 60 sessions.
    cutoff = px["Date"].max() - pd.Timedelta(days=120)
    recent = px[px["Date"] >= cutoff].copy()
    recent["tv"] = recent["Close"] * recent["Volume"]
    liq = recent.groupby("Symbol")["tv"].median()
    keep = liq[liq >= 10_000_000].index
    syms = sorted(set(pd.Series(list(keep)).astype(str).str.upper()))
    # Instrument filter AFTER the value gate, because the value gate cannot do this job:
    # bonds pass it on face value. Structure is the discriminator.
    equities = [s for s in syms if not is_non_equity(s)]
    dropped = len(syms) - len(equities)
    if dropped:
        print(
            f"  dropped {dropped} non-equity instruments (bonds/G-secs/T-bills) "
            f"that cleared the value gate"
        )
    return equities


def _validate_progress(df, prev_df, new_field_names):
    """Sanity-check that a checkpoint is real forward progress, not a
    silently-degenerate collection -- a DIFFERENT failure mode than the
    Blocked/MAX_CONSECUTIVE_EMPTY circuit breaker above, which only catches
    connection-level refusal. A host that returns 200s with a changed page
    layout (regex stops matching) would sail past that breaker while
    quietly writing empty-field rows -- this catches THAT.

    Checked only on rows ADDED since the previous checkpoint, not the whole
    accumulated file -- diluting a live problem under thousands of already-
    good historical rows would hide exactly the failure this exists to
    catch. Returns a list of warning strings (empty list = healthy)."""
    warnings_found = []
    if df.empty:
        warnings_found.append("checkpoint produced ZERO rows total")
        return warnings_found
    n_new = len(df) - (len(prev_df) if prev_df is not None else 0)
    if prev_df is not None and n_new <= 0:
        warnings_found.append(f"no new rows since the last checkpoint (still {len(df):,} total)")
        return warnings_found
    recent = df.tail(n_new) if n_new > 0 else df
    if len(recent) >= 20:
        for field in new_field_names:
            if field in recent.columns:
                pct = recent[field].notna().mean() * 100
                if pct == 0:
                    warnings_found.append(
                        f"{field}: 0% populated over the last {len(recent):,} new rows"
                    )
    return warnings_found


def main():
    ap = argparse.ArgumentParser(description="Collect India historical financials from screener.in")
    ap.add_argument("--tickers", nargs="*", help="explicit NSE symbols (else the India universe)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of tickers (testing)")
    ap.add_argument(
        "--refresh-thin", action="store_true",
        help="re-fetch tickers whose stored rows lack cfo / screener.in source / >=3 fiscal years")
    ap.add_argument(
        "--liquid-only", action="store_true", help="only names present in cache_seed/ltm/IN.parquet"
    )
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    import screener_in_auth as sess_mod

    sess_mod.session()  # login once (cached); raises if creds missing/invalid

    universe = _universe(args)
    if args.limit:
        universe = universe[: args.limit]

    done, existing = set(), []
    if os.path.exists(OUT):
        prev = pd.read_parquet(OUT)
        done = set(prev["ticker"].astype(str).str.upper())
        existing = [prev]

        # --refresh-thin: a ticker counts as "done" only if its stored rows are
        # actually USABLE. Presence alone means done otherwise, so the tickers
        # carrying yfinance-sourced rows (no cfo, ~2 fiscal years) are skipped
        # forever and the panel can never become backtestable. Measured
        # 2026-07-21: cfo present on 153 of 1,654 PIT rows, so Piotroski tests 2
        # and 4 are uncomputable for 91% of names and the score cannot be formed
        # at all. Re-fetching those from screener.in is the entire point.
        if getattr(args, "refresh_thin", False):
            g = prev.copy()
            g["_tk"] = g["ticker"].astype(str).str.upper()
            has_cfo = g.groupby("_tk")["cfo"].apply(lambda x: x.notna().any())
            nyr = g.groupby("_tk")["fy_end"].nunique()
            # Usable = has cfo AND >=3 fiscal years. The source label is NOT part
            # of the test.
            #
            # It used to also require source == "screener_in", which excluded
            # THIS collector's own output: rows written by the current path carry
            # a null source, so 201 fully-populated tickers (cfo 94.7%,
            # borrowings 88.3%, median 10 FY) were classed as thin and queued for
            # re-fetch. At ~50-155 requests before screener.in starts blocking,
            # that is two entire sessions spent re-downloading good data.
            #
            # The source check was standing in for "not a yfinance-only row", but
            # cfo presence already establishes that — yfinance supplies cfo on
            # 2.9% of rows. Measured 2026-07-21: usable 281 -> 524, re-fetch
            # 1,575 -> 1,332.
            keep = set(has_cfo.index[(has_cfo) & (nyr >= 3)])
            print(f"  --refresh-thin: {len(keep)} tickers usable, "
                  f"{len(done) - len(keep)} to re-fetch")
            done = keep
    todo = [t for t in universe if t not in done]
    print(
        f"screener.in history: {len(universe)} tickers, {len(done)} already done, "
        f"{len(todo)} to fetch (~{len(todo)*_RATE/60:.0f} min at {_RATE}s/req)"
    )

    def _checkpoint():
        df = (
            pd.concat(existing + [pd.DataFrame(rows)], ignore_index=True)
            if (existing or rows)
            else pd.DataFrame()
        )
        if not df.empty:
            # Newly fetched rows carry fy_end/filed as STRINGS; rows already on
            # disk carry timestamps. Concatenating gives an object column and
            # pyarrow refuses to write it ("object of type str cannot be
            # converted to int"), which kills the run at the first checkpoint —
            # i.e. after the fetches have been paid for and before anything is
            # saved. Coerce both to datetime before writing.
            for _c in ("fy_end", "filed", "filed_nse"):
                if _c in df.columns:
                    df[_c] = pd.to_datetime(df[_c], errors="coerce")
            # Re-fetched tickers appear twice; keep the richer screener.in row.
            if {"ticker", "fy_end"} <= set(df.columns):
                df["_pref"] = (df.get("source", "").astype(str) == "screener_in").astype(int)
                df = (df.sort_values("_pref")
                        .drop_duplicates(subset=["ticker", "fy_end"], keep="last")
                        .drop(columns=["_pref"]))
            os.makedirs(OUT_DIR, exist_ok=True)  # survive a mid-run dir wipe
            df.to_parquet(OUT, index=False)
        return df

    # Fields this session's shareholding/dividend wiring added -- what
    # _validate_progress() watches for silent zero-coverage.
    _NEW_FIELDS = ("dividend_amount", "promoter_holding", "fii_holding",
                   "dii_holding", "public_holding", "num_shareholders")

    rows, n_ok, t0, _consec_empty = [], 0, time.time(), 0
    _last_checkpoint_t = time.time()
    _last_checkpoint_df = existing[0] if existing else None
    for i, tk in enumerate(todo, 1):
        time.sleep(_RATE)
        # ONE retry on empty before it counts against the circuit breaker. Proven
        # transient, not a block: 500002 (ABB India, a large well-covered company —
        # not a genuine data gap) returned empty once during a live run, then
        # succeeded on an immediate manual re-fetch seconds later. The endpoint is
        # occasionally flaky under sustained load; a single retry absorbs that
        # without weakening real-block detection, since a genuine block fails the
        # retry too and still counts.
        try:
            r = collect_ticker(sess_mod, tk)
        except Blocked:
            print(
                f"\n  ABORT: host refused the connection at {tk} — hard block, "
                f"not retrying. Collected {n_ok} before this."
            )
            _checkpoint()
            break
        except Exception:
            r = None
        if not r:
            time.sleep(_RATE * 2)
            try:
                r = collect_ticker(sess_mod, tk)
            except Blocked:
                print(
                    f"\n  ABORT: host refused the connection at {tk} (on retry) — "
                    f"hard block, not retrying. Collected {n_ok} before this."
                )
                _checkpoint()
                break
            except Exception:
                r = None
        got = bool(r)
        if got:
            rows.extend(r)
            n_ok += 1
        # CIRCUIT BREAKER. Consecutive empties (after the retry above already absorbed
        # one-off flakiness) mean the session died or the host is blocking; continuing
        # just deepens the block and produces a fake progress bar. Checked AFTER the
        # fetch (needs this iteration's result, not the prior one — the previous
        # version referenced `got`/`_consec_empty` before either was ever assigned, an
        # unconditional NameError that meant this collector could not run at all).
        _consec_empty = 0 if got else _consec_empty + 1
        if _consec_empty >= MAX_CONSECUTIVE_EMPTY:
            print(
                f"\n  ABORT: {_consec_empty} consecutive tickers returned nothing "
                f"(each retried once) — session dead or host blocking. "
                f"Collected {n_ok} before this."
            )
            _checkpoint()
            break
        due_by_count = i % 100 == 0 or i == len(todo)
        due_by_time = (time.time() - _last_checkpoint_t) >= _CHECKPOINT_INTERVAL_SEC
        if due_by_count or due_by_time:
            df = _checkpoint()
            trigger = "count" if due_by_count else "10min"
            print(f"  [{trigger}] {i}/{len(todo)} | {n_ok} with data | {len(df)} rows | {time.time()-t0:.0f}s")
            for w in _validate_progress(df, _last_checkpoint_df, _NEW_FIELDS):
                print(f"  ⚠ VALIDATION: {w}")
            _last_checkpoint_df = df
            _last_checkpoint_t = time.time()
    print(f"done → {os.path.relpath(OUT, BASE)}")


if __name__ == "__main__":
    main()
