# Tests for the walk-forward backtest — pure logic, no network.
import numpy as np

import backtest as bt


def test_edge_metrics():
    m = bt.edge_metrics([10, 20, -5], [4, 4, 4])
    assert m["trades"] == 3
    assert m["avg_ret"] == round((10 + 20 - 5) / 3, 2)
    assert m["edge"] == round(m["avg_ret"] - 4, 2)
    assert m["win_rate"] == round(2 / 3, 3)  # 10>4, 20>4, -5<4
    assert bt.edge_metrics([], [])["trades"] == 0


def test_pit_is_causal_and_needs_history():
    c = np.linspace(100, 200, 260)
    assert bt._pit(c, 150) is None  # <200 bars
    f = bt._pit(c, 259)
    assert f is not None and f["sma50"] > f["sma200"]  # uptrend
    # causal: features at t must not depend on data after t
    f_a = bt._pit(c, 220)
    c2 = c.copy()
    c2[221:] = 0
    assert bt._pit(c2, 220)["sma50"] == f_a["sma50"]


def test_screen_predicates():
    up = {
        "sma50": 110,
        "sma200": 100,
        "sma50_prev": 95,
        "sma200_prev": 100,
        "rsi": 60,
        "pct_from_high": -1,
        "ret126": 40,
    }
    assert bt.SCREENS["golden_state"](up) is True
    assert bt.SCREENS["golden_crossover"](up) is True  # crossed up
    assert bt.SCREENS["near_high"](up) is True
    assert bt.SCREENS["rsi_oversold"](up) is False


def test_backtest_screen_on_synthetic(monkeypatch):
    # one always-rising symbol → golden_state fires, forward returns positive
    c = np.linspace(100, 300, 400)
    df = __import__("pandas").DataFrame({"Close": c})
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: {"UP": df})
    r = bt.backtest_screen("IN", "golden_state", horizon=21, step=21)
    assert r["trades"] > 0 and r["avg_ret"] > 0


# ── BUG: picks were compared with the market mean pooled over ALL dates ────────
def _dated(closes, index=None):
    import pandas as pd

    idx = index if index is not None else pd.bdate_range("2015-01-01", periods=len(closes))
    return pd.DataFrame({"Close": np.asarray(closes, dtype=float)}, index=idx)


def test_identical_universe_has_zero_edge(monkeypatch):
    """Every symbol follows the same up-then-down path, so each pick earns exactly
    the equal-weight market return of its own window: true edge 0. Averaging the
    market over all windows showed a phantom edge for a screen firing in up-legs."""
    path = np.concatenate([np.linspace(100, 300, 400), np.linspace(300, 100, 400)])
    data = {s: _dated(path) for s in ("A", "B", "C")}
    monkeypatch.setattr(bt.datalink, "load_market", lambda m, tier=None: data)
    r = bt.backtest_screen("IN", "golden_state", horizon=21, step=21)
    assert r["trades"] > 0
    assert abs(r["edge"]) <= 0.01
    assert r["win_rate"] == 0.0


def test_market_is_paired_by_calendar_date(monkeypatch):
    """Names listed on different dates but priced identically on shared dates:
    paired by calendar window the edge is 0 (not by row offset, not pooled)."""
    path = np.concatenate([np.linspace(100, 300, 500), np.linspace(300, 100, 500)])
    early = _dated(path)
    late = _dated(path[300:], index=early.index[300:])
    monkeypatch.setattr(
        bt.datalink, "load_market", lambda m, tier=None: {"EARLY": early, "LATE": late}
    )
    r = bt.backtest_screen("IN", "golden_state", horizon=21, step=1)
    assert r["trades"] > 0
    assert abs(r["edge"]) <= 0.01
