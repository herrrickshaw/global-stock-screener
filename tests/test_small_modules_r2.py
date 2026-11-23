"""smart_holdings, factor_analysis, total_return, portfolio_analytics.analyze (offline, faked deps)."""

import sys
import types

import numpy as np
import pandas as pd
import pytest

import factor_analysis as fa
import portfolio_analytics as pa
import smart_holdings as sh
import total_return as tr


def fake(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


# ---------------- smart_holdings ----------------
def test_net_buy_aggregation_variants():
    deals = [
        {"symbol": " abc ", "buySell": "BUY", "quantity": 100},
        {"Symbol": "ABC", "BuySell": "SELL", "Quantity": 30},
        {"SYMBOL": "ABC", "dealType": "Buy", "qty": "5"},
        {"symbol": "XYZ", "buySell": "HOLD", "quantity": 99},  # neither B nor S -> 0
        {"symbol": "", "buySell": "BUY", "quantity": 7},  # blank dropped
        {"symbol": "NOQ", "buySell": "BUY"},  # missing qty -> 0
        {"symbol": "SEL", "buySell": "SELL", "quantity": 4},
    ]
    net = sh.net_buy_by_symbol(deals)
    assert net == {"ABC": 75.0, "XYZ": 0.0, "NOQ": 0.0, "SEL": -4.0}
    assert sh.net_buy_by_symbol([]) == {}


def test_conviction_screen_order_and_threshold():
    deals = [
        {"symbol": "A", "buySell": "BUY", "quantity": 10},
        {"symbol": "B", "buySell": "BUY", "quantity": 50},
        {"symbol": "C", "buySell": "BUY", "quantity": 0},
        {"symbol": "D", "buySell": "SELL", "quantity": 5},
    ]
    assert sh.conviction_screen(deals) == ["B", "A"]  # strictly > 0
    assert sh.conviction_screen(deals, min_net=10) == ["B"]  # strictly > min_net
    assert sh.conviction_screen([]) == []


def test_fetch_bulk_deals(monkeypatch, capsys):
    df = pd.DataFrame({"symbol": ["A", "B"]})
    fake(monkeypatch, "nsepython", get_bulkdeals=lambda: df)
    assert sh.fetch_bulk_deals() == [{"symbol": "A"}, {"symbol": "B"}]
    assert "bulk deals fetched: 2" in capsys.readouterr().out
    fake(monkeypatch, "nsepython", get_bulkdeals=lambda: [{"symbol": "Z"}])
    assert sh.fetch_bulk_deals(verbose=False) == [{"symbol": "Z"}]
    fake(monkeypatch, "nsepython", get_bulkdeals=lambda: None)
    assert sh.fetch_bulk_deals(verbose=False) == []
    fake(monkeypatch, "nsepython")  # no get_bulkdeals
    assert sh.fetch_bulk_deals(verbose=False) == []
    fake(monkeypatch, "nsepython", get_bulkdeals=lambda: 1 / 0)
    assert sh.fetch_bulk_deals(verbose=False) == []
    monkeypatch.setitem(sys.modules, "nsepython", None)
    assert sh.fetch_bulk_deals() == []
    assert capsys.readouterr().out.strip() == "bulk deals fetched: 0"


def test_smart_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sh"])
    assert sh.main() == 0
    assert "(run --fetch; source may be throttled)" in capsys.readouterr().out
    rows = [{"symbol": f"S{i:02d}", "buySell": "BUY", "quantity": 100 - i} for i in range(25)]
    monkeypatch.setattr(sh, "fetch_bulk_deals", lambda: rows)
    monkeypatch.setattr(sys, "argv", ["sh", "--fetch"])
    sh.main()
    out = capsys.readouterr().out
    assert out.startswith("bulk-deal net buyers: ['S00', 'S01'")
    assert "S19" in out and "S20" not in out  # first 20 only


# ---------------- factor_analysis ----------------
def test_ols_recovers_coefficients():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 2, 50)
    s = rng.normal(0, 1, 50)
    y = 0.5 + 1.2 * m - 0.3 * s
    r = fa.ols(list(y), {"Mkt-RF": list(m), "SMB": list(s)})
    assert r["alpha"] == 0.5 and r["betas"] == {"Mkt-RF": 1.2, "SMB": -0.3}
    assert r["r2"] == 1.0 and r["n"] == 50


def test_ols_constant_y_has_zero_r2_denominator_guard():
    r = fa.ols([2.0] * 10, {"X": list(range(10))})
    assert r["alpha"] == 2.0 and r["betas"] == {"X": 0.0} and r["r2"] == 1.0


def test_analyze_returns_alignment_and_min_length():
    rows = [{"Mkt-RF": float(i), "SMB": 0.1 * (i % 3), "HML": 0.2 * (i % 2)} for i in range(10)]
    y = [1.0 + 2.0 * r["Mkt-RF"] for r in rows]
    out = fa.analyze_returns(y, rows)
    assert out["n"] == 10 and out["betas"]["Mkt-RF"] == 2.0 and out["alpha"] == 1.0
    # lengths differ: aligned on the most recent n
    out2 = fa.analyze_returns(y[2:], rows)
    assert out2["n"] == 8 and out2["betas"]["Mkt-RF"] == 2.0
    out3 = fa.analyze_returns(y, rows[:7])
    assert out3["n"] == 7
    # exactly 6 allowed, 5 not
    assert fa.analyze_returns(y[:6], rows[:6])["n"] == 6
    assert fa.analyze_returns(y[:5], rows[:5]) == {}
    assert fa.analyze_returns([], []) == {}


def test_load_ff3_coerces_numeric(tmp_path, monkeypatch):
    p = tmp_path / "ff3.parquet"
    pd.DataFrame(
        {"Mkt-RF": ["1.5", "x"], "SMB": [1, 2], "HML": ["0.1", "0.2"], "RF": ["0.01", None]}
    ).to_parquet(p)
    monkeypatch.setattr(fa, "FF3", p)
    d = fa._load_ff3()
    assert d["Mkt-RF"].iloc[0] == 1.5 and np.isnan(d["Mkt-RF"].iloc[1])
    assert d["RF"].iloc[0] == 0.01 and np.isnan(d["RF"].iloc[1])
    assert d["SMB"].dtype.kind in "if"


def test_factor_main_modes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["fa", "--demo"])
    assert fa.main() == 0
    out = capsys.readouterr().out
    assert "'Mkt-RF'" in out and "'SMB'" in out and "'n': 60" in out
    p = tmp_path / "ff3.parquet"
    pd.DataFrame(
        {"Mkt-RF": [1.0, 2.0, 3.0], "SMB": [0.0] * 3, "HML": [0.0] * 3, "RF": [0.0] * 3}
    ).to_parquet(p)
    monkeypatch.setattr(fa, "FF3", p)
    monkeypatch.setattr(sys, "argv", ["fa"])
    fa.main()
    assert (
        capsys.readouterr().out.strip()
        == "provide a return series via analyze_returns(); FF3 rows: 3"
    )


# ---------------- total_return ----------------
def test_total_return_math_edges():
    assert tr.total_return_from([100, 110, 121]) == 21.0
    assert tr.total_return_from([0, 5]) == 0.0  # non-positive start
    assert (
        tr.total_return_from([100, 0, 50]) == -100.0
    )  # price fell to 0; the 0->50 step is skipped (no div by 0)
    assert tr.total_return_from([100, 100, 100], [0, 5, 5]) == 10.25
    assert tr.price_return_from([100]) == 0.0
    assert tr.price_return_from([0, 5]) == 0.0
    assert tr.price_return_from([100, 150]) == 50.0
    assert tr.price_return_from([50, 40]) == -20.0


class FakeHist:
    def __init__(self, df):
        self.df = df
        self.asked = []

    def __call__(self, ticker):
        outer = self
        outer.asked.append(("ticker", ticker))

        class T:
            def history(self_, period, auto_adjust):
                outer.asked.append(("history", period, auto_adjust))
                return outer.df

        return T()


def test_total_return_fetch(monkeypatch):
    df = pd.DataFrame({"Close": [100.0, 100.0], "Dividends": [0.0, 5.0]})
    h = FakeHist(df)
    fake(monkeypatch, "yfinance", Ticker=h)
    r = tr.total_return("TCS", "IN", "6mo")
    assert r == {"symbol": "TCS", "price_return": 0.0, "total_return": 5.0, "dividend_uplift": 5.0}
    assert h.asked == [("ticker", "TCS.NS"), ("history", "6mo", False)]
    tr.total_return("AAPL", "US")
    assert h.asked[2] == ("ticker", "AAPL") and h.asked[3] == ("history", "1y", False)
    tr.total_return("X", "ZZ")  # unknown market -> bare ticker
    assert ("ticker", "X") in h.asked
    # no Dividends column -> price only
    fake(monkeypatch, "yfinance", Ticker=FakeHist(pd.DataFrame({"Close": [100.0, 110.0]})))
    r2 = tr.total_return("A", "US")
    assert r2["total_return"] == 10.0 and r2["dividend_uplift"] == 0.0
    # empty history / errors -> {}
    fake(monkeypatch, "yfinance", Ticker=FakeHist(pd.DataFrame()))
    assert tr.total_return("A") == {}
    fake(monkeypatch, "yfinance", Ticker=lambda t: 1 / 0)
    assert tr.total_return("A") == {}


def test_total_return_suffix_table():
    assert tr._SUFFIX["IN"] == ".NS" and tr._SUFFIX["US"] == "" and tr._SUFFIX["UK"] == ".L"
    assert tr._SUFFIX["JP"] == ".T" and tr._SUFFIX["KR"] == ".KS" and len(tr._SUFFIX) == 20


def test_total_return_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["tr", "--symbol", "TCS"])
    monkeypatch.setattr(
        tr,
        "total_return",
        lambda s, m, p: (
            {"symbol": s, "price_return": 1, "total_return": 3, "dividend_uplift": 2}
            if (m, p) == ("IN", "1y")
            else {}
        ),
    )
    assert tr.main() == 0
    assert capsys.readouterr().out.strip() == "TCS: price 1% | total 3% | dividend uplift 2%"
    monkeypatch.setattr(sys, "argv", ["tr", "--symbol", "TCS", "--market", "US"])
    tr.main()
    assert capsys.readouterr().out.strip() == "no data (yfinance throttled/unavailable)"


# ---------------- portfolio_analytics.analyze ----------------
def eval_frame(rows):
    return pd.DataFrame(rows, columns=["Symbol", "Signal", "PE", "Flags"])


def install(monkeypatch, frame, smap=None, sector_raises=False):
    calls = []
    pe = types.ModuleType("portfolio_evaluator")

    def evaluate(syms, market, fetch, verbose):
        calls.append((syms, market, fetch, verbose))
        return frame

    pe.evaluate = evaluate
    monkeypatch.setitem(sys.modules, "portfolio_evaluator", pe)
    sm = types.ModuleType("sector_map")

    def sector_map(market):
        if sector_raises:
            raise RuntimeError("x")
        return smap or {}

    sm.sector_map = sector_map
    monkeypatch.setitem(sys.modules, "sector_map", sm)
    return calls


def test_weights_edge_cases():
    assert pa._weights([]) == {}
    assert pa._weights({}) == {}
    assert pa._weights({"a": 0, "b": 0}) == {"A": 0.0, "B": 0.0}  # zero total guard
    assert pa._hhi({}) == 0.0
    assert pa._hhi({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}) == 0.333


def test_rebalance_boundaries_and_flags():
    rows = [
        {
            "symbol": "EQ",
            "weight": 0.10,
            "signal": "BUY",
            "flags": "",
            "sector": "S1",
        },  # == cap: ok
        {"symbol": "OV", "weight": 0.1001, "signal": "HOLD", "flags": "", "sector": "S2"},
        {"symbol": "FL", "weight": 0.01, "signal": "HOLD", "flags": "IMPAIRED x", "sector": "?"},
        {"symbol": "SL", "weight": 0.5, "signal": "SELL", "flags": "", "sector": ""},
    ]
    acts = pa.rebalance_actions(rows)
    assert acts == [
        "REDUCE OV — 10% > 10% single-name cap",
        "TRIM/EXIT FL — HOLD IMPAIRED x",
        "TRIM/EXIT SL — SELL",
    ]
    # sector cap strict, '?' and '' ignored
    rows2 = [{"symbol": "A", "weight": 0.3, "signal": "BUY", "flags": "", "sector": "Tech"}]
    assert pa.rebalance_actions(rows2, max_name=1.0) == []
    assert pa.rebalance_actions(rows2, max_name=1.0, max_sector=0.29) == [
        "REDUCE sector Tech — 30% > 29% sector cap"
    ]
    rows3 = [{"symbol": "A", "weight": 0.9, "signal": "BUY", "flags": "", "sector": "?"}]
    assert pa.rebalance_actions(rows3, max_name=1.0) == []
    assert (
        pa.rebalance_actions([{"symbol": "A", "weight": 0.9, "signal": "BUY"}], max_name=1.0) == []
    )


def test_analyze_full(monkeypatch, capsys):
    frame = eval_frame(
        [
            ("AAA", "BUY", 20.0, ""),
            ("BBB", "SELL", 40.0, "IMPAIRED"),
            ("CCC", "HOLD", float("nan"), ""),
            ("DDD", "HOLD", 1000.0, ""),  # PE >= 1000 excluded from weighted PE
        ]
    )
    calls = install(monkeypatch, frame, {"AAA": "Tech", "BBB": "Tech", "CCC": "Bank"})
    out = pa.analyze({"aaa": 2, "bbb": 1, "ccc": 1, "ddd": 1, "eee": 1}, "IN")
    assert calls[0][0] == ["AAA", "BBB", "CCC", "DDD", "EEE"] and calls[0][1:] == (
        "IN",
        False,
        False,
    )
    assert out["n"] == 5 and out["market"] == "IN"
    # weights /6: AAA .333, others .1667; weighted PE over AAA,BBB = (20*2+40*1)/3
    assert out["weighted_pe"] == round((20 * 2 + 40 * 1) / 3, 1)
    assert out["signal_mix"] == {"BUY": 0.333, "HOLD": 0.333, "SELL": 0.167, "NO DATA": 0.167}
    assert out["top_sectors"]["Tech"] == pytest.approx(0.5)
    assert out["flagged"] == ["BBB"]
    assert out["name_hhi"] == round((2 / 6) ** 2 + 4 * (1 / 6) ** 2, 3)
    assert any("TRIM/EXIT BBB" in a for a in out["actions"])
    assert any("REDUCE sector Tech — 50% > 30% sector cap" == a for a in out["actions"])
    txt = capsys.readouterr().out
    assert "=== Portfolio analytics (IN) — 5 holdings ===" in txt
    assert "weighted P/E: 26.7" in txt and "rebalance actions:" in txt and "• TRIM/EXIT BBB" in txt


def test_analyze_quiet_balanced_and_sector_failure(monkeypatch, capsys):
    syms = [f"S{i:02d}" for i in range(12)]
    frame = eval_frame([(s, "BUY", 10.0, "") for s in syms])
    install(monkeypatch, frame, sector_raises=True)
    out = pa.analyze(syms, "US", verbose=False)
    assert capsys.readouterr().out == ""
    assert out["top_sectors"] == {"?": pytest.approx(1.0)}
    assert out["actions"] == []  # 1/12 = 8.3% < 10%; '?' sector exempt
    assert out["weighted_pe"] == 10.0 and out["flagged"] == []
    # balanced verbose output says none
    pa.analyze(syms, "US")
    assert "(none — book looks balanced)" in capsys.readouterr().out


def test_analyze_no_pe_gives_none_and_top5_sectors(monkeypatch):
    syms = [f"S{i}" for i in range(7)]
    frame = eval_frame([(s, "HOLD", float("nan"), "") for s in syms])
    install(monkeypatch, frame, {s: f"Sec{i}" for i, s in enumerate(syms)})
    out = pa.analyze(syms, verbose=False)
    assert out["weighted_pe"] is None and len(out["top_sectors"]) == 5
    assert out["signal_mix"] == {"HOLD": 1.0}


def test_analyze_pe_zero_excluded(monkeypatch):
    frame = eval_frame([("A", "BUY", 0.0, ""), ("B", "BUY", -5.0, ""), ("C", "BUY", 999.0, "")])
    install(monkeypatch, frame)
    assert pa.analyze(["A", "B", "C"], verbose=False)["weighted_pe"] == 999.0


def test_portfolio_main(monkeypatch):
    seen = []
    monkeypatch.setattr(pa, "analyze", lambda h, m: seen.append((h, m)))
    monkeypatch.setattr(sys, "argv", ["pa", "--tickers", "A, B,,C", "--market", "US"])
    assert pa.main() == 0
    assert seen == [(["A", "B", "C"], "US")]
