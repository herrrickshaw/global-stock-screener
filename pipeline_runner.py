#!/usr/bin/env python3
# pipeline_runner.py
# ==================
# Daily orchestrator behind the 08:30 dashboard. Two stages, because the scan
# stack + market data live in the main working tree while the dashboard + CI
# gates live on the `mailer` branch:
#
#   --stage scan    (run in the scan working tree): incremental data update,
#                    run the combined-report scans, capture news mood + pipeline
#                    execution status.
#   --stage checks  (run in the dashboard worktree): lint / tests / governance +
#                    integrity / import-smoke — "check the code for flaws".
#
# Both stages read+merge results/pipeline_status.json so the dashboard renders one
# unified status. Every step is best-effort (report & continue): a failure is
# recorded as ok=False with detail, never raised.
# ⚠️ Research/education only. Not advice.

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
from pathlib import Path
from typing import Dict, List


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_status(out_dir: Path) -> dict:
    p = out_dir / "pipeline_status.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _write_status(out_dir: Path, status: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "pipeline_status.json"
    status["generated"] = _now()
    p.write_text(json.dumps(status, indent=2))
    return p


# ── stage: scan (data update + scans + news + pipeline health) ─────────────────
def _data_update(markets: List[str]) -> dict:
    detail = []
    ok = True
    try:
        import market_memory as mm

        res = mm.update_all(markets, period="5d", verbose=False)
        for r in res if isinstance(res, list) else []:
            detail.append(f"{r.get('market', '?')}: +{r.get('added', r.get('rows', 0))}")
    except Exception as e:  # noqa: BLE001
        ok = False
        detail.append(f"data update error: {str(e)[:80]}")
    try:
        import serving_layer as sl

        sl.refresh(markets, verbose=False)
        detail.append("serving refreshed")
    except Exception as e:  # noqa: BLE001
        detail.append(f"serving refresh skipped: {str(e)[:60]}")
    return {"ok": ok, "detail": "; ".join(detail) or "no update"}


def _run_scans(markets: List[str], repo: Path) -> dict:
    written, ok = [], True
    for m in markets:
        try:
            r = subprocess.run(
                ["python3", "daily_combined_report.py", "--market", m, "--html", "--run-fresh"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if r.returncode == 0:
                written.append(m)
            else:
                ok = False
        except Exception:  # noqa: BLE001
            ok = False
    return {"ok": ok, "detail": f"combined report written for: {', '.join(written) or 'none'}"}


def _news(markets: List[str]) -> Dict[str, dict]:
    out = {}
    try:
        import news_feeds
    except Exception:
        return out
    for m in markets:
        try:
            d = news_feeds.market_mood(m)
            if d:
                out[m] = d
        except Exception:
            continue
    return out


def _pipeline_health(markets: List[str]) -> dict:
    """Did data + serving views end up in a usable state?"""
    try:
        import market_memory as mm

        df = mm.status(markets)
        empty = [str(r["market"]) for _, r in df.iterrows() if int(r["rows"]) == 0]
        ok = len(empty) < len(df)  # at least some tier has data
        detail = "all tiers populated" if not empty else f"empty: {', '.join(sorted(set(empty)))}"
        return {"ok": ok, "detail": detail}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"status error: {str(e)[:80]}"}


def stage_scan(markets: List[str], repo: Path, out_dir: Path) -> dict:
    status = _read_status(out_dir)
    status["data_update"] = _data_update(markets)
    status["scans"] = _run_scans(markets, repo)
    status["pipeline"] = _pipeline_health(markets)
    status["news"] = _news(markets)
    _write_status(out_dir, status)
    return status


# ── stage: checks (lint / tests / governance+integrity / imports) ──────────────
def _sh(cmd: List[str], cwd: Path, timeout: int = 900):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def _check_lint(repo: Path) -> dict:
    try:
        ruff = _sh(["python3", "-m", "ruff", "check", "."], repo, 300)
        black = _sh(["python3", "-m", "black", "--check", "."], repo, 300)
        ok = ruff.returncode == 0 and black.returncode == 0
        if ok:
            return {"ok": True, "detail": "ruff + black clean"}
        issues = (ruff.stdout + ruff.stderr).strip().splitlines()[-1:] or ["ruff/black issues"]
        return {"ok": False, "detail": issues[-1][:120]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"lint error: {str(e)[:80]}"}


def _check_tests(repo: Path) -> dict:
    try:
        r = _sh(["python3", "-m", "pytest", "-q"], repo, 1200)
        tail = (r.stdout + r.stderr).strip().splitlines()
        summary = tail[-1] if tail else ""
        return {"ok": r.returncode == 0, "detail": summary[:120]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"pytest error: {str(e)[:80]}"}


def _check_governance(repo: Path) -> dict:
    detail, ok = [], True
    try:
        import governance as g

        res = g.run(verbose=False)
        passed = sum(1 for okk, _ in res.values() if okk)
        ok = passed == len(res)
        detail.append(f"governance {passed}/{len(res)}")
    except Exception as e:  # noqa: BLE001
        ok = False
        detail.append(f"governance error: {str(e)[:50]}")
    try:
        import integrity

        rc = integrity.verify(verbose=False)
        if rc != 0:
            ok = False
            detail.append("integrity drift")
        else:
            detail.append("integrity ok")
    except Exception as e:  # noqa: BLE001
        detail.append(f"integrity skipped: {str(e)[:40]}")
    return {"ok": ok, "detail": "; ".join(detail)}


def _check_imports(repo: Path) -> dict:
    import importlib

    failed = []
    for py in sorted(repo.glob("*.py")):
        mod = py.stem
        if mod in {"pipeline_runner", "setup", "conftest"}:
            continue
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{mod} ({str(e)[:30]})")
    if failed:
        return {"ok": False, "detail": f"{len(failed)} import failure(s): " + "; ".join(failed[:5])}
    return {"ok": True, "detail": "all modules import"}


def stage_checks(repo: Path, out_dir: Path) -> dict:
    status = _read_status(out_dir)
    status["code_health"] = {
        "lint": _check_lint(repo),
        "tests": _check_tests(repo),
        "governance": _check_governance(repo),
        "imports": _check_imports(repo),
    }
    _write_status(out_dir, status)
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Daily dashboard pipeline orchestrator")
    ap.add_argument("--stage", choices=["scan", "checks", "all"], default="all")
    ap.add_argument("--market", nargs="*", default=["IN", "US"])
    ap.add_argument("--repo", default=".", help="working tree with the code for this stage")
    ap.add_argument("--out", default="results", help="dir holding pipeline_status.json")
    a = ap.parse_args(argv)
    repo, out = Path(a.repo).resolve(), Path(a.out).resolve()

    if a.stage in ("scan", "all"):
        s = stage_scan(a.market, repo, out)
        print(f"scan stage: data={s['data_update']['ok']} scans={s['scans']['ok']}")
    if a.stage in ("checks", "all"):
        s = stage_checks(repo, out)
        ch = s["code_health"]
        print("checks stage: " + " ".join(f"{k}={v['ok']}" for k, v in ch.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
