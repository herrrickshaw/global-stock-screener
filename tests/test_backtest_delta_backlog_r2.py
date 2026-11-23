"""backtest (guards, run_all, CLI), watchlist_delta (snapshot/report/main), backlog (store/CLI)."""

import datetime as dt
import json
import sys
import types

import numpy as np
import pandas as pd
import pytest

import backlog as bl
import backtest as bt
import watchlist_delta as wd

# ---------------- backtest ----------------


def test_pit_guards_and_values():
    assert bt._pit(np.ones(300), 199) is None
    assert bt._pit(np.ones(300), 200) is not None
    c = np.ones(300)
    c[250] = 0.0
    assert bt._pit(c, 250) is None  # last price <= 0
    c2 = np.ones(300)
    c2[250] = -1.0
    assert bt._pit(c2, 250) is None
    flat = bt._pit(np.full(300, 10.0), 250)
    assert flat["rsi"] == 100.0  # no down moves -> 100
    assert flat["pct_from_high"] == 0.0 and flat["ret126"] == 0.0
    assert flat["sma50"] == 10.0 and flat["sma200"] == 10.0
    # only losses -> RSI 0
    series = np.linspace(500, 100, 300)
    down = bt._pit(series, 299)
    assert down["rsi"] == pytest.approx(0.0)
    assert down["pct_from_high"] == pytest.approx((100 / series[-252:].max() - 1) * 100)  # 252-bar high
    # ret126 uses 126 bars back
    ramp = np.arange(1.0, 301.0)
    f = bt._pit(ramp, 299)
    assert f["ret126"] == pytest.approx((300 / 175 - 1) * 100)
    # the as-of window excludes the future
    assert bt._pit(ramp, 250)["sma50"] == pytest.approx(ramp[201:251].mean())


def test_screen_predicate_boundaries():
    base = dict(sma50=2, sma200=1, sma50_prev=1, sma200_prev=1, rsi=50, pct_from_high=0, ret126=0)
    S = bt.SCREENS
    assert S["golden_state"](base) and not S["golden_state"]({**base, "sma50": 1})
    assert S["golden_crossover"](base)
    assert S["golden_crossover"]({**base, "sma50_prev": 1, "sma200_prev": 1})  # prev equal counts
    assert not S["golden_crossover"]({**base, "sma50_prev": 1.5})
    assert S["near_high"]({**base, "pct_from_high": -3}) and not S["near_high"]({**base, "pct_from_high": -3.01})
    assert S["rsi_oversold"]({**base, "rsi": 29.99}) and not S["rsi_oversold"]({**base, "rsi": 30})
    assert S["momentum"]({**base, "ret126": 25.01}) and not S["momentum"]({**base, "ret126": 25})
    assert not S["momentum"]({**base, "ret126": 30, "sma50": 1})


def test_edge_metrics_values():
    m = bt.edge_metrics([10.0, 2.0, -1.0], [5.0, 2.0, 3.0])
    assert m == {"trades": 3, "avg_ret": 3.67, "mkt_ret": 3.33, "edge": 0.33, "win_rate": 0.333}
    assert bt.edge_metrics([], [])["trades"] == 0
    assert bt.edge_metrics([], []) == {"trades": 0, "avg_ret": 0.0, "mkt_ret": 0.0, "edge": 0.0, "win_rate": 0.0}


def _df(closes):
    idx = pd.bdate_range("2015-01-01", periods=len(closes))
    return pd.DataFrame({"Close": np.asarray(closes, float)}, index=idx)


def test_unknown_screen_raises(monkeypatch):
    with pytest.raises(ValueError, match="unknown screen"):
        bt.backtest_screen("IN", "nope")


def test_backtest_falls_back_to_default_tier_and_skips_short_and_none(monkeypatch):
    seen = []

    def load(m, tier=None):
        seen.append(tier)
        if tier == "ltm":
            return {}
        return {"LONG": _df(np.linspace(100, 300, 400)), "SHORT": _df(np.linspace(1, 2, 221)), "NONE": None}

    monkeypatch.setattr(bt.datalink, "load_market", load)
    r = bt.backtest_screen("IN", "golden_state", horizon=21, step=21)
    assert seen == ["ltm", None]
    assert r["trades"] > 0
    assert (r["market"], r["screen"], r["horizon"]) == ("IN", "golden_state", 21)
    # SHORT has exactly 200+21 bars: below the 200+horizon+1 requirement -> skipped
    only_short = {"SHORT": _df(np.linspace(1, 2, 221))}
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: only_short)
    assert bt.backtest_screen("IN", "golden_state")["trades"] == 0
    # exactly 222 bars is accepted (no pick may fire but data is processed)
    ok = {"S": _df(np.linspace(1, 2, 222))}
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: ok)
    assert bt.backtest_screen("IN", "golden_state")["trades"] >= 0


def test_max_symbols_limits_universe(monkeypatch):
    data = {f"S{i}": _df(np.linspace(100, 300, 400) + i) for i in range(4)}
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: data)
    full = bt.backtest_screen("IN", "golden_state")
    one = bt.backtest_screen("IN", "golden_state", max_symbols=1)
    assert one["trades"] * 4 == full["trades"]


def test_glitch_bars_are_dropped(monkeypatch):
    c = np.linspace(100, 300, 400)
    c[260:] *= 20  # >500% jump inside the first horizon windows
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: {"G": _df(c)})
    r = bt.backtest_screen("IN", "golden_state", horizon=21, step=1)
    assert r["trades"] > 0
    assert abs(r["avg_ret"]) <= 500


def test_horizon_changes_eligibility(monkeypatch):
    data = {"A": _df(np.linspace(100, 300, 260))}
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: data)
    short = bt.backtest_screen("IN", "golden_state", horizon=5, step=1)
    long_ = bt.backtest_screen("IN", "golden_state", horizon=40, step=1)
    assert short["trades"] > long_["trades"] > 0
    assert short["trades"] == len(range(200, 260 - 5 - 1))
    assert long_["trades"] == len(range(200, 260 - 40 - 1))


def test_run_all_sorts_and_prints(monkeypatch, capsys):
    edges = {"golden_state": 1.0, "golden_crossover": 3.0, "near_high": 2.0, "rsi_oversold": -1.0, "momentum": 0.5}
    monkeypatch.setattr(
        bt,
        "backtest_screen",
        lambda m, s, h: {"screen": s, "trades": 1, "avg_ret": 0, "mkt_ret": 0, "edge": edges[s], "win_rate": 0},
    )
    df = bt.run_all("IN", 10)
    assert list(df["screen"]) == ["golden_crossover", "near_high", "golden_state", "momentum", "rsi_oversold"]
    out = capsys.readouterr().out
    assert "Walk-forward backtest — IN (10d hold)" in out and "edge = screen avg" in out
    bt.run_all("IN", 10, verbose=False)
    assert capsys.readouterr().out == ""


def test_backtest_main(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(bt, "run_all", lambda m, h: calls.append(("all", m, h)))
    monkeypatch.setattr(
        bt,
        "backtest_screen",
        lambda m, s, h: {"trades": 4, "avg_ret": 1.5, "mkt_ret": 1.0, "edge": 0.5, "win_rate": 0.25},
    )
    monkeypatch.setattr(sys, "argv", ["bt"])
    assert bt.main() == 0 and calls == [("all", "IN", 21)]
    monkeypatch.setattr(sys, "argv", ["bt", "--all", "--screen", "momentum", "--market", "US", "--horizon", "5"])
    bt.main()
    assert calls[-1] == ("all", "US", 5)
    monkeypatch.setattr(sys, "argv", ["bt", "--screen", "momentum", "--market", "US"])
    bt.main()
    assert capsys.readouterr().out.strip() == "momentum on US: 4 trades, avg 1.5% vs mkt 1.0% → edge 0.5%, win 25%"


# ---------------- watchlist_delta ----------------


@pytest.fixture
def snap(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "SNAP", tmp_path)
    return tmp_path


def write(snap, market, day, rows):
    pd.DataFrame(rows, columns=["Symbol", "Signal", "Flags"]).to_parquet(
        snap / f"{market}_{day}.parquet", index=False
    )


def test_last_two_sorted_and_market_scoped(snap):
    for d in ("2026-01-03", "2026-01-01", "2026-01-02"):
        write(snap, "IN", d, [("A", "BUY", "")])
    write(snap, "US", "2026-02-01", [("A", "BUY", "")])
    assert [p.name for p in wd._last_two("IN")] == ["IN_2026-01-02.parquet", "IN_2026-01-03.parquet"]
    assert wd._last_two("XX") == []


def test_diff_new_symbol_and_flag_rules(snap):
    write(snap, "IN", "2026-01-01", [("A", "HOLD", "WEAK"), ("B", "HOLD", ""), ("D", "BUY", "")])
    write(
        snap,
        "IN",
        "2026-01-02",
        [
            ("A", "HOLD", "WEAK PLEDGE"),  # new risk flag PLEDGE only
            ("B", "HOLD", "NOISE"),  # new non-risk flag -> ignored
            ("C", "BUY", ""),  # brand-new symbol: from "—", counts as UPGRADE to BUY
            ("D", "BUY", "DISTRIBUTION IMPAIRED"),
            ("E", "NO DATA", ""),  # new, rank 0 vs "—" (0): not > -> DOWNGRADE
        ],
    )
    d, s = wd.diff("IN")
    rows = {r.Symbol: r for r in d.itertuples()}
    assert set(rows) == {"A", "C", "D", "E"}
    assert rows["A"].Change == "NEW-FLAG" and rows["A"].Flags == "PLEDGE"
    assert rows["C"].Change == "UPGRADE" and rows["C"].From == "—"
    assert rows["D"].Change == "NEW-FLAG" and set(rows["D"].Flags.split()) == {"DISTRIBUTION", "IMPAIRED"}
    assert rows["E"].Change == "DOWNGRADE"
    assert s == {"dates": "2026-01-01 → 2026-01-02", "new_buys": 1, "downgrades": 1, "new_flags": 2}


def test_diff_no_changes_has_zero_summary(snap):
    write(snap, "IN", "2026-01-01", [("A", "BUY", "")])
    write(snap, "IN", "2026-01-02", [("A", "BUY", "")])
    d, s = wd.diff("IN")
    assert d.empty and s == {"dates": "2026-01-01 → 2026-01-02", "new_buys": 0, "downgrades": 0, "new_flags": 0}


def test_diff_upgrade_not_to_buy_isnt_new_buy(snap):
    write(snap, "IN", "2026-01-01", [("A", "SELL", ""), ("B", "HOLD", "")])
    write(snap, "IN", "2026-01-02", [("A", "HOLD", ""), ("B", "BUY", "")])
    d, s = wd.diff("IN")
    assert dict(zip(d.Symbol, d.Change)) == {"A": "UPGRADE", "B": "UPGRADE"}
    assert s["new_buys"] == 1 and s["downgrades"] == 0


def test_report_prints(snap, capsys):
    d = wd.report("IN")
    assert d.empty
    assert "need 2 snapshots — run --snapshot on two different days" in capsys.readouterr().out
    write(snap, "IN", "2026-01-01", [("A", "HOLD", "")])
    write(snap, "IN", "2026-01-02", [("A", "BUY", "")])
    d = wd.report("IN")
    out = capsys.readouterr().out
    assert "Watchlist delta (IN) 2026-01-01 → 2026-01-02" in out
    assert "new BUYs 1 · downgrades 0 · new risk flags 0" in out
    assert "UPGRADE" in out
    assert len(d) == 1
    wd.report("IN", verbose=False)
    assert capsys.readouterr().out == ""
    write(snap, "IN", "2026-01-03", [("A", "BUY", "")])
    wd.report("IN")
    out = capsys.readouterr().out
    assert "new BUYs 0" in out and "UPGRADE" not in out and "Symbol" not in out


def test_report_head_limit_30(snap, capsys):
    write(snap, "IN", "2026-01-01", [(f"S{i:02d}", "HOLD", "") for i in range(35)])
    write(snap, "IN", "2026-01-02", [(f"S{i:02d}", "BUY", "") for i in range(35)])
    wd.report("IN")
    out = capsys.readouterr().out
    assert "S29" in out and "S30" not in out


def _install_snapshot_fakes(monkeypatch, serving_df, evaluated):
    pe = types.ModuleType("portfolio_evaluator")
    pe.calls = []

    def evaluate(syms, market, fetch, verbose):
        pe.calls.append((list(syms), market, fetch, verbose))
        return evaluated

    pe.evaluate = evaluate
    sl = types.ModuleType("serving_layer")
    sl.serving = lambda m: serving_df
    monkeypatch.setitem(sys.modules, "portfolio_evaluator", pe)
    monkeypatch.setitem(sys.modules, "serving_layer", sl)
    return pe


def test_snapshot_top_by_turnover(snap, monkeypatch, capsys):
    srv = pd.DataFrame({"Symbol": ["A", "B", "C"], "Turnover_USD": [1.0, 9.0, 5.0]})
    ev = pd.DataFrame(
        {"Symbol": ["B", "C"], "Signal": ["BUY", "HOLD"], "Flags": ["", ""], "Extra": [1, 2]}
    )
    pe = _install_snapshot_fakes(monkeypatch, srv, ev)
    p = wd.snapshot("IN", top=2)
    assert pe.calls == [(["B", "C"], "IN", False, False)]
    assert p == snap / f"IN_{dt.date.today().isoformat()}.parquet"
    saved = pd.read_parquet(p)
    assert list(saved.columns) == ["Symbol", "Signal", "Flags"]
    assert "snapshot[IN]: 2 decisions" in capsys.readouterr().out
    wd.snapshot("IN", top=2, verbose=False)
    assert capsys.readouterr().out == ""


def test_snapshot_without_turnover_and_empty(snap, monkeypatch):
    srv = pd.DataFrame({"Symbol": ["A", "B", "C"]})
    ev = pd.DataFrame({"Symbol": ["A"], "Signal": ["BUY"], "Flags": [""]})
    pe = _install_snapshot_fakes(monkeypatch, srv, ev)
    wd.snapshot("US", top=2, verbose=False)
    assert pe.calls[0][0] == ["A", "B"]
    _install_snapshot_fakes(monkeypatch, pd.DataFrame(), ev)
    with pytest.raises(RuntimeError, match="no serving view for US"):
        wd.snapshot("US")


def test_watchlist_main(monkeypatch):
    calls = []
    monkeypatch.setattr(wd, "snapshot", lambda m: calls.append(("s", m)))
    monkeypatch.setattr(wd, "report", lambda m: calls.append(("r", m)))
    monkeypatch.setattr(sys, "argv", ["wd"])
    assert wd.main() == 0 and calls == [("r", "IN")]
    monkeypatch.setattr(sys, "argv", ["wd", "--snapshot", "--market", "US"])
    wd.main()
    assert calls[1:] == [("s", "US"), ("r", "US")]


# ---------------- backlog ----------------


@pytest.fixture
def store(tmp_path, monkeypatch):
    p = tmp_path / "backlog.json"
    monkeypatch.setattr(bl, "STORE", p)
    return p


def test_load_seeds_when_missing_and_on_corrupt(store):
    items = bl._load()
    assert items == bl._SEED and items is not bl._SEED
    assert json.loads(store.read_text()) == bl._SEED
    store.write_text("{not json")
    assert bl._load() == bl._SEED
    assert json.loads(store.read_text()) == bl._SEED  # re-seeded


def test_load_returns_existing_and_save_roundtrip(store):
    bl._save([{"id": "X"}])
    assert bl._load() == [{"id": "X"}]
    assert json.loads(store.read_text()) == [{"id": "X"}]


def test_next_pi_capacity_boundary_and_skipping():
    mk = lambda i, v, s: {"id": i, "value": v, "time_criticality": 0, "risk": 0, "job_size": s, "status": "todo"}
    items = [mk("A", 10, 5), mk("B", 9, 5), mk("C", 8, 5), mk("D", 100, 20), mk("E", 1, 1)]
    done = {"id": "Z", "value": 99, "time_criticality": 0, "risk": 0, "job_size": 1, "status": "done"}
    plan = bl.next_pi(items + [done], capacity=15)
    # ranked by WSJF: E(1.0)... compute: A2, B1.8, C1.6, D5, E1 -> D too big, A,B,C = 15 (exact fit), E won't fit
    assert [i["id"] for i in plan] == ["A", "B", "C"]
    assert [i["id"] for i in bl.next_pi(items, capacity=16)] == ["A", "B", "C", "E"]
    assert bl.next_pi(items, capacity=0) == []
    assert [i["id"] for i in bl.next_pi(items)] == ["A", "B", "C"]  # default capacity 15


def test_backlog_main_modes(store, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bl"])
    assert bl.main() == 0
    out = capsys.readouterr().out
    assert "=== Program backlog (WSJF-ranked) ===" in out
    assert "delivered this PI (velocity): 15 pts / 3 features" in out
    assert "F-D1" not in out  # done items not listed

    monkeypatch.setattr(sys, "argv", ["bl", "--json"])
    assert bl.main() == 0
    data = json.loads(capsys.readouterr().out)
    assert all(d["status"] == "todo" for d in data)
    assert [d["wsjf"] for d in data] == sorted((d["wsjf"] for d in data), reverse=True)

    monkeypatch.setattr(sys, "argv", ["bl", "--pi", "--capacity", "8"])
    assert bl.main() == 0
    out = capsys.readouterr().out
    assert "Proposed next PI (capacity 8 pts)" in out
    committed = int(out.split("committed: ")[1].split(" pts")[0])
    assert 0 < committed <= 8
