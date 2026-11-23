"""query.py with a fake duckdb module: view registration, SQL building, CLI."""

import builtins
import sys
import types

import pandas as pd
import pytest

import query as q


class FakeCon:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchdf(self):
        return pd.DataFrame({"x": [1]})


@pytest.fixture
def fake_duck(monkeypatch):
    c = FakeCon()
    mod = types.ModuleType("duckdb")
    mod.connect = lambda path: (c.calls.append(("connect", path)), c)[1]
    monkeypatch.setitem(sys.modules, "duckdb", mod)
    monkeypatch.setattr(q, "_CON", None)
    return c


def test_require_raises_clear_message(monkeypatch):
    real = builtins.__import__

    def imp(name, *a, **k):
        if name == "duckdb":
            raise ImportError("nope")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", imp)
    with pytest.raises(RuntimeError, match="pip install duckdb") as ei:
        q._require()
    assert isinstance(ei.value.__cause__, ImportError)
    monkeypatch.setattr(q, "_CON", None)
    with pytest.raises(RuntimeError, match="needs DuckDB"):
        q.con()


def test_con_no_data_registers_no_views_and_caches(fake_duck, monkeypatch, tmp_path):
    monkeypatch.setattr(q, "HERE", tmp_path)
    monkeypatch.setattr(q, "LTM_GLOB", str(tmp_path / "cache_seed" / "ltm" / "*.parquet"))
    c = q.con()
    assert c is fake_duck
    assert fake_duck.calls == [("connect", ":memory:")]
    assert q.con() is c and len(fake_duck.calls) == 1  # cached


def test_con_prefers_hive_parts(fake_duck, monkeypatch, tmp_path):
    parts = tmp_path / "cache_seed" / "ltm_parts" / "market=IN" / "year=2025"
    parts.mkdir(parents=True)
    (parts / "a.parquet").write_bytes(b"")
    ltm = tmp_path / "cache_seed" / "ltm"
    ltm.mkdir()
    (ltm / "IN.parquet").write_bytes(b"")
    monkeypatch.setattr(q, "HERE", tmp_path)
    monkeypatch.setattr(q, "LTM_GLOB", str(ltm / "*.parquet"))
    q.con()
    views = [c[0] for c in fake_duck.calls[1:]]
    assert len(views) == 1
    assert "CREATE VIEW ltm" in views[0] and "hive_partitioning=true" in views[0]
    assert "RENAME (market AS Market)" in views[0]


def test_con_parts_dir_without_parquet_falls_back_to_single_files(fake_duck, monkeypatch, tmp_path):
    (tmp_path / "cache_seed" / "ltm_parts").mkdir(parents=True)
    ltm = tmp_path / "cache_seed" / "ltm"
    ltm.mkdir()
    (ltm / "IN.parquet").write_bytes(b"")
    monkeypatch.setattr(q, "HERE", tmp_path)
    monkeypatch.setattr(q, "LTM_GLOB", str(ltm / "*.parquet"))
    q.con()
    views = [c[0] for c in fake_duck.calls[1:]]
    assert len(views) == 1 and "filename=true" in views[0] and "AS Market" in views[0]
    assert str(ltm) in views[0]


def test_con_registers_serving_view(fake_duck, monkeypatch, tmp_path):
    srv = tmp_path / "cache_seed" / "serving"
    srv.mkdir(parents=True)
    (srv / "IN.parquet").write_bytes(b"")
    monkeypatch.setattr(q, "HERE", tmp_path)
    monkeypatch.setattr(q, "LTM_GLOB", str(tmp_path / "cache_seed" / "ltm" / "*.parquet"))
    monkeypatch.setattr(q, "SERVING_GLOB", str(srv / "*.parquet"))
    q.con()
    views = [c[0] for c in fake_duck.calls[1:]]
    assert len(views) == 1 and views[0].startswith("CREATE VIEW serving")


def test_sql_param_binding(monkeypatch):
    c = FakeCon()
    monkeypatch.setattr(q, "con", lambda: c)
    q.sql("SELECT 1")
    q.sql("SELECT ?", ["a"])
    q.sql("SELECT 2", [])
    assert c.calls == [("SELECT 1", None), ("SELECT ?", ["a"]), ("SELECT 2", None)]
    assert list(q.sql("SELECT 1")["x"]) == [1]


@pytest.fixture
def sqlrec(monkeypatch):
    rec = []
    monkeypatch.setattr(
        q, "sql", lambda query, params=None: (rec.append((query, params)), pd.DataFrame())[1]
    )
    return rec


def test_bars_minimal_and_full(sqlrec):
    q.bars("TCS")
    sql, params = sqlrec[-1]
    assert "WHERE Symbol = ? ORDER BY Date" in sql and params == ["TCS"]
    q.bars("TCS", "IN", "2025-01-01", "2025-06-30")
    sql, params = sqlrec[-1]
    assert (
        "WHERE Symbol = ? AND Market = ? AND Date >= CAST(? AS DATE) AND Date <= CAST(? AS DATE)"
        in sql
    )
    assert params == ["TCS", "IN", "2025-01-01", "2025-06-30"]
    q.bars("TCS", end="2025-06-30")
    sql, params = sqlrec[-1]
    assert "Date <= CAST" in sql and "Date >=" not in sql and params == ["TCS", "2025-06-30"]
    q.bars("TCS", start="2025-01-01")
    sql, params = sqlrec[-1]
    assert "Date >= CAST" in sql and "Date <=" not in sql
    q.bars("TCS", market="")  # falsy market ignored
    assert sqlrec[-1][1] == ["TCS"]


def test_latest_default_and_filter(sqlrec):
    q.latest("IN")
    sql, params = sqlrec[-1]
    assert "rn = 1 AND (TRUE) ORDER BY Symbol" in sql and params == ["IN"]
    q.latest("US", where="Close > 10")
    sql, params = sqlrec[-1]
    assert "rn = 1 AND (Close > 10)" in sql and params == ["US"]


def test_main_default_and_custom_query(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(q, "sql", lambda s: (seen.append(s), pd.DataFrame({"a": [1, 2]}))[1])
    monkeypatch.setattr(sys, "argv", ["q"])
    assert q.main() == 0
    assert "GROUP BY 1 ORDER BY 2 DESC" in seen[0] and "n_syms" in seen[0]
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["a"] and [l.strip() for l in out.splitlines()[1:]] == [
        "1",
        "2",
    ]
    monkeypatch.setattr(sys, "argv", ["q", "SELECT 7"])
    q.main()
    assert seen[-1] == "SELECT 7"
