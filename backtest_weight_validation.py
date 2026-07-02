#!/usr/bin/env python3
# backtest_weight_validation.py  —  Roadmap Phase 4
# =================================================
# Does a fundamentals composite actually separate winners from losers over the
# deep LTM window? Builds a z-scored composite from the metrics Phase 3 flags as
# significant (sign-aligned by their correlation), sorts the universe into
# quintiles, and reports realised performance per quintile plus the top-minus-
# bottom (Q5−Q1) spread — the out-of-sample "edge" of the fundamental signal.
#
#   python3 backtest_weight_validation.py --market US --target cagr
#
# CAVEAT: uses CURRENT fundamentals against realised history (look-ahead +
# survivorship). Directional evidence, not a tradeable result. Coverage is limited
# to cached fundamentals. ⚠️ Research/education only. Not advice.

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import correlation_analysis as ca

FUND_DIR = Path(__file__).parent / "cache_seed" / "fundamentals"


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0.0


def build_composite(market: str, target: str = "cagr", top_k: int = 6, p_max: float = 0.10):
    """Composite = mean of sign-aligned z-scores of the most-correlated metrics."""
    corr = ca.analyse(market, target)
    if corr.empty:
        return None, None, corr
    picks = corr[corr["p_value"] <= p_max].head(top_k)
    if picks.empty:
        picks = corr.head(top_k)  # fall back to strongest even if not significant
    fund = pd.read_parquet(FUND_DIR / f"{market}.parquet")
    perf = ca._perf_features(market)
    merged = perf.merge(fund, on="Symbol", how="inner")
    comp = pd.Series(0.0, index=merged.index)
    used = []
    for _, r in picks.iterrows():
        col = r["metric"]
        if col not in merged:
            continue
        comp = comp + np.sign(r["spearman_rho"]) * _zscore(
            pd.to_numeric(merged[col], errors="coerce")
        )
        used.append(col)
    merged["composite"] = comp
    return merged, used, picks


def validate(market: str, target: str = "cagr", q: int = 5) -> dict:
    merged, used, picks = build_composite(market, target)
    if merged is None or merged.empty:
        return {"market": market, "error": "no fundamentals/perf overlap"}
    m = merged.dropna(subset=["composite", target])
    if len(m) < q * 2:
        return {"market": market, "error": f"too few names ({len(m)}) for {q}-tiles"}
    m = m.sort_values("composite")
    m["quintile"] = pd.qcut(m["composite"].rank(method="first"), q, labels=range(1, q + 1))
    table = m.groupby("quintile", observed=True)[target].agg(["mean", "median", "count"])
    q_top, q_bot = table.loc[q, "mean"], table.loc[1, "mean"]
    return {
        "market": market,
        "target": target,
        "metrics_used": used,
        "n": int(len(m)),
        "table": table,
        "spread_top_minus_bottom": float(q_top - q_bot),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 4 — fundamentals-composite quintile backtest")
    ap.add_argument("--market", default="US")
    ap.add_argument("--target", default="cagr", choices=ca.PERF)
    ap.add_argument("--quantiles", type=int, default=5)
    a = ap.parse_args()
    r = validate(a.market, a.target, a.quantiles)
    if "error" in r:
        print(f"{a.market}: {r['error']}")
        return 0
    print(f"\n{a.market} — fundamentals composite vs {a.target} (n={r['n']})")
    print(f"  metrics: {', '.join(r['metrics_used'])}")
    tbl = r["table"].copy()
    tbl["mean"] = (tbl["mean"] * 100).round(1)
    tbl["median"] = (tbl["median"] * 100).round(1)
    print(tbl.to_string())
    sp = r["spread_top_minus_bottom"] * 100
    print(
        f"\n  Q{a.quantiles}−Q1 spread ({a.target}): {sp:+.1f} pp "
        f"→ {'signal separates winners' if sp > 0 else 'no/negative separation'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
