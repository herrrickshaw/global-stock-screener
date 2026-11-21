# Proof tests for the 2026-10-25 static-analysis sweep (import-smoke, deptry, S608).
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_market_data_repository_module_imports():
    # Before the fix: TypeError "Cannot create a consistent MRO for bases ABC, Repository"
    # because Repository already derives from ABC.
    sys.modules.pop("src.market_data.domain.repositories", None)
    mod = importlib.import_module("src.market_data.domain.repositories")
    assert mod.MarketDataRepository.__abstractmethods__  # still abstract


def test_vcrud_index_ltm_finds_db_handler_in_vcrud_bin(monkeypatch):
    # db_handler/vcrud_manager live in .vcrud_bin/; the script must put that dir on
    # sys.path (as ingest_gate.py does) or it fails at import with ModuleNotFoundError.
    fake = types.ModuleType("psycopg2")
    fake.extras = types.ModuleType("psycopg2.extras")
    fake.extras.RealDictCursor = object
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
    for m in ("vcrud_index_ltm", "db_handler", "vcrud_manager"):
        monkeypatch.delitem(sys.modules, m, raising=False)
    mod = importlib.import_module("vcrud_index_ltm")
    assert hasattr(mod, "main")


def test_requirements_declare_unguarded_third_party_imports():
    # ml_factor_screener.py / f1_hyperparameter_tuning.py import sklearn at top level and
    # deep_prices.py / local_collect.py import curl_cffi at top level; neither was pinned.
    req = (ROOT / "requirements.txt").read_text().lower()
    assert "scikit-learn" in req
    assert "curl_cffi" in req or "curl-cffi" in req


class _FakeCon:
    def __init__(self):
        self.calls = []

    def execute(self, q, params=None):
        self.calls.append((q, params))
        return self

    def fetchdf(self):
        import pandas as pd

        return pd.DataFrame()


def test_query_bars_binds_user_values(monkeypatch):
    query = importlib.import_module("query")
    fake = _FakeCon()
    monkeypatch.setattr(query, "con", lambda: fake)
    evil = "TCS' OR 1=1 --"
    query.bars(evil, "IN", start="2025-01-01", end="2025-12-31")
    q, params = fake.calls[-1]
    assert evil not in q, "symbol was interpolated into SQL text"
    assert params is not None and evil in params and "IN" in params


def test_query_latest_binds_market(monkeypatch):
    query = importlib.import_module("query")
    fake = _FakeCon()
    monkeypatch.setattr(query, "con", lambda: fake)
    evil = "IN' OR 1=1 --"
    query.latest(evil)
    q, params = fake.calls[-1]
    assert evil not in q
    assert params is not None and evil in params
