"""Boundary tests for the fundamental strategy modules and strategy base helpers."""

import pandas as pd
import pytest

import strategies as st
from strategies import bluest_blue_chips as bbc
from strategies import debt_reduction as dr
from strategies import dividend_yield as dy
from strategies import golden_crossover as gc
from strategies import loss_to_profit as ltp
from strategies import magic_formula as mf
from strategies.base import Result, StockData, cagr, pct_change, safe, sma


def S(**f):
    return StockData("T", "IN", fundamentals=f)


# ---------------- base ----------------
def test_stockdata_accessors():
    s = StockData("T")
    assert s.f("x") is None and s.f("x", 5) == 5
    assert s.close is None and s.ltp is None
    assert StockData("T", ohlcv=pd.DataFrame()).close is None
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.5]})
    s2 = StockData("T", ohlcv=df)
    assert s2.ltp == 3.5 and list(s2.close) == [1.0, 2.0, 3.5]


def test_result_row():
    r = Result("A", "x", True, score=1.5, metrics={"m": 2}, note="n")
    assert r.row() == {
        "Symbol": "A",
        "Strategy": "x",
        "Pass": "YES",
        "Score": 1.5,
        "m": 2,
        "Note": "n",
    }
    assert Result("A", "x", False).row()["Pass"] == "NO"


def test_base_helpers():
    assert pct_change(110, 100) == pytest.approx(10)
    assert pct_change(90, -100) == pytest.approx(190)
    assert pct_change(None, 1) is None and pct_change(1, None) is None and pct_change(1, 0) is None
    assert cagr(200, 100, 1) == pytest.approx(100)
    assert cagr(0, 100, 5) is None and cagr(100, 0, 5) is None
    assert cagr(100, -5, 5) is None and cagr(100, 50, 0) is None
    assert sma(None, 3) is None
    assert sma(pd.Series([1, 2]), 3) is None
    assert sma(pd.Series([1, 2, 3, 5]), 2) == 4.0
    assert sma(pd.Series([1, 2, 3]), 3) == 2.0
    assert safe("3") == 3.0 and safe(None) is None and safe("x") is None
    assert safe(float("nan")) is None


# ---------------- bluest blue chips ----------------
def good_bbc(**over):
    f = dict(market_cap_cr=3000, roe=15, profit_growth=10, pe=20, industry_pe=20)
    f.update(over)
    return S(**f)


def test_bbc_boundaries_pass():
    r = bbc.screen(good_bbc())
    assert r.passed and r.note == "blue chip" and r.score == 15.0
    assert r.metrics["MCap_cr"] == 3000 and r.metrics["PE"] == 20


@pytest.mark.parametrize(
    "over,key",
    [
        ({"market_cap_cr": 2999.9}, "MCap>3000cr"),
        ({"roe": 14.99}, "ROE>=15"),
        ({"profit_growth": 9.99}, "ProfitGrowth>=10"),
        ({"pe": 20.01}, "ValAttractive"),
        ({"pe": 0}, "ValAttractive"),
        ({"pe": -3}, "ValAttractive"),
    ],
)
def test_bbc_each_check_fails(over, key):
    r = bbc.screen(good_bbc(**over))
    assert not r.passed and r.metrics[key] == 0 and r.note == ""
    assert (
        sum(r.metrics[k] for k in ("MCap>3000cr", "ProfitGrowth>=10", "ROE>=15", "ValAttractive"))
        == 3
    )


def test_bbc_fallbacks():
    # raw INR market cap converted to crore (1e7)
    assert bbc.screen(good_bbc(market_cap_cr=None, market_cap=3e10)).metrics["MCap_cr"] == 3000
    assert bbc.screen(good_bbc(market_cap_cr=None, market_cap=0)) is None  # falsy -> None
    assert bbc.screen(good_bbc(market_cap_cr=None)) is None
    assert bbc.screen(good_bbc(roe=None)) is None
    # eps_growth used when profit_growth missing / zero
    assert bbc.screen(good_bbc(profit_growth=None, eps_growth=12)).metrics["ProfitGrowth%"] == 12
    r = bbc.screen(good_bbc(profit_growth=None))
    assert r.metrics["ProfitGrowth>=10"] == 0
    # no industry PE: any positive PE is attractive
    assert bbc.screen(good_bbc(industry_pe=None, pe=500)).metrics["ValAttractive"] == 1
    assert bbc.screen(good_bbc(pe=None)).metrics["ValAttractive"] == 0


# ---------------- debt reduction ----------------
def test_dr_decreasing_helper():
    # helper is unused by screen(); it reports "each value greater than the next" in list order
    assert dr._decreasing([5, 4, 3]) is True
    assert dr._decreasing([3, 4, 5]) is False
    assert dr._decreasing([3, 3]) is False
    assert dr._decreasing([5]) is False
    assert dr._decreasing([5, None, 3]) is True  # None filtered
    assert dr._decreasing([]) is False


def test_dr_pass_with_capex_or_gross_block():
    # newest-first debt: 50 < 80 < 100 means debt fell
    r = dr.screen(S(debt_history=[50, 80, 100], capex_history=[9, 7]))
    assert r.passed and r.note == "deleveraging+capex"
    assert r.metrics == {"DebtFalling": 1, "DebtChange%": -50.0, "CapacityExpanding": 1}
    assert r.score == 50.0
    r2 = dr.screen(S(debt_history=[50, 80], gross_block_history=[200, 100]))
    assert r2.passed and r2.metrics["CapacityExpanding"] == 1


def test_dr_fail_modes():
    # debt rising
    r = dr.screen(S(debt_history=[100, 80], capex_history=[9, 7]))
    assert not r.passed and r.metrics["DebtFalling"] == 0 and r.note == ""
    # equal consecutive debt is not falling (strict)
    assert (
        dr.screen(S(debt_history=[80, 80, 100], capex_history=[9, 7])).metrics["DebtFalling"] == 0
    )
    # capex not expanding: equal, shrinking, or too short
    assert (
        dr.screen(S(debt_history=[50, 80], capex_history=[7, 7])).metrics["CapacityExpanding"] == 0
    )
    assert (
        dr.screen(S(debt_history=[50, 80], capex_history=[5, 7])).metrics["CapacityExpanding"] == 0
    )
    assert dr.screen(S(debt_history=[50, 80], capex_history=[9])).metrics["CapacityExpanding"] == 0
    assert (
        dr.screen(S(debt_history=[50, 80], gross_block_history=[100])).metrics["CapacityExpanding"]
        == 0
    )
    assert not dr.screen(S(debt_history=[50, 80])).passed


def test_dr_insufficient_and_zero_base():
    assert dr.screen(S()) is None
    assert dr.screen(S(debt_history=[5])) is None
    assert dr.screen(S(debt_history=[5, float("nan"), None])) is None
    # oldest debt 0 -> no pct change, score 0
    r = dr.screen(S(debt_history=[0, 0], capex_history=[2, 1]))
    assert r.metrics["DebtChange%"] is None and r.score == 0
    assert not r.passed


# ---------------- dividend yield ----------------
def test_dy_boundaries():
    r = dy.screen(S(dividend_yield=2.0, dividend_pay_years=3))
    assert r.passed and r.note == "income" and r.score == 2.0
    assert r.metrics == {"DividendYield%": 2.0, "PayYears": 3, "Consistent": 1}
    assert not dy.screen(S(dividend_yield=1.99, dividend_pay_years=3)).passed
    r2 = dy.screen(S(dividend_yield=5, dividend_pay_years=2))
    assert not r2.passed and r2.metrics["Consistent"] == 0
    assert dy.screen(S()) is None


def test_dy_history_fallback():
    r = dy.screen(S(dividend_yield=3, dividend_history=[1, 0.5, 2, 0, None, -1]))
    assert r.metrics["PayYears"] == 3 and r.passed
    r2 = dy.screen(S(dividend_yield=3, dividend_history=[1, 0, 2]))
    assert r2.metrics["PayYears"] == 2 and not r2.passed
    r3 = dy.screen(S(dividend_yield=3))
    assert r3.metrics["PayYears"] == 0 and not r3.passed
    # explicit pay years wins over history
    assert (
        dy.screen(S(dividend_yield=3, dividend_pay_years=0, dividend_history=[1, 1, 1])).metrics[
            "PayYears"
        ]
        == 0
    )


# ---------------- loss to profit ----------------
def test_ltp_turnaround():
    r = ltp.screen(S(quarterly_net_income=[10, -5, 3, 4]))
    assert r.passed and r.note == "turnaround" and r.score == 10
    assert (
        r.metrics["PriorQ_NI"] == -5 and r.metrics["WasLoss"] == 1 and r.metrics["NowProfit"] == 1
    )
    assert r.metrics["Swing%"] == 300.0


def test_ltp_window_and_signs():
    # loss 4 quarters back is outside the 3-quarter lookback
    r = ltp.screen(S(quarterly_net_income=[10, 2, 3, 4, -9]))
    assert not r.passed and r.metrics["WasLoss"] == 0
    # loss exactly 3 back is inside
    assert ltp.screen(S(quarterly_net_income=[10, 2, 3, -4])).passed
    # latest zero is not profit
    r2 = ltp.screen(S(quarterly_net_income=[0, -1]))
    assert not r2.passed and r2.metrics["NowProfit"] == 0
    # latest negative
    assert not ltp.screen(S(quarterly_net_income=[-1, -2])).passed
    # prior zero -> no swing
    assert ltp.screen(S(quarterly_net_income=[5, 0, -1])).metrics["Swing%"] is None
    assert ltp.screen(S(quarterly_net_income=[-4, 2])).score == -4


def test_ltp_insufficient():
    assert ltp.screen(S()) is None
    assert ltp.screen(S(quarterly_net_income=[5])) is None
    assert ltp.screen(S(quarterly_net_income=[5, None, float("nan")])) is None


# ---------------- magic formula ----------------
def test_mf_boundaries():
    r = mf.screen(S(earnings_yield=8, roc=15))
    assert r.passed and r.note == "cheap+quality" and r.score == 23.0
    assert not mf.screen(S(earnings_yield=7.99, roc=15)).passed
    assert not mf.screen(S(earnings_yield=8, roc=14.99)).passed


def test_mf_derived_and_fallback():
    r = mf.screen(S(ebit=10, enterprise_value=100, roc=20))
    assert r.metrics == {"EarningsYield%": 10.0, "ROC%": 20.0}
    assert mf.screen(S(ebit=10, enterprise_value=100, roce=18)).metrics["ROC%"] == 18.0
    assert mf.screen(S(earnings_yield=9, roc=20, roce=1)).metrics["ROC%"] == 20.0
    assert mf.screen(S(ebit=10, enterprise_value=0, roc=20)) is None
    assert mf.screen(S(ebit=10, roc=20)) is None
    assert mf.screen(S(earnings_yield=9)) is None


# ---------------- golden crossover ----------------
def _prices(vals):
    return StockData("T", ohlcv=pd.DataFrame({"Close": [float(v) for v in vals]}))


def test_gc_short_history_none():
    assert gc.screen(_prices([1] * 204)) is None
    assert gc.screen(StockData("T")) is None


def test_gc_cross_and_states():
    # long flat then sharp rise on the last bar: 50dma crosses above 200dma
    vals = [100.0] * 249 + [100.0 + 2000]
    r = gc.screen(_prices(vals))
    assert r.passed and r.note == "GOLDEN_CROSS" and r.metrics["DMA50_above_200"] is True
    assert r.score > 0
    # already above for a while: not a fresh cross
    vals2 = [100.0] * 100 + [200.0] * 150
    r2 = gc.screen(_prices(vals2))
    assert not r2.passed and r2.note == "above"
    vals3 = [200.0] * 100 + [100.0] * 150
    r3 = gc.screen(_prices(vals3))
    assert not r3.passed and r3.note == "below" and r3.score < 0
    # exactly equal averages: no cross, not above
    r4 = gc.screen(_prices([100.0] * 250))
    assert not r4.passed and r4.note == "below" and r4.score == 0


def test_run_all_filters_and_isolates(monkeypatch):
    s = S(roe=20)
    only_price = st.run_all(s, only_needs="price")
    assert all(st.STRATEGIES[k].META["needs"] == "price" for k in only_price)

    class Boom:
        META = {"needs": "price"}

        @staticmethod
        def screen(_):
            raise RuntimeError("x")

    monkeypatch.setitem(st.STRATEGIES, "boom", Boom)
    assert "boom" not in st.run_all(s)
    assert "boom" not in st.run_all(s, only_needs="price")
