#!/usr/bin/env python3
"""
etl_pipeline.py — Extract / Transform / Load orchestrator for the daily
multi-market report (India · US · Europe).

Why
---
The legacy `daily_pipeline.sh` is a linear script that mixes fetching, scoring
and reporting. This wraps the same building blocks (market scans, the sentiment
pipeline, emerging-market fundamentals, the report builder) in an explicit ETL
shape with a curated data lake and per-run lineage, so each stage is
independently runnable, idempotent, and resumable.

Layout (all under ./data, LFS-tracked where it matters)
    data/raw/<date>/        EXTRACT  — raw pulls (universe snapshots, scan xlsx refs, news json)
    data/curated/           TRANSFORM— normalized parquet tables (fundamentals, darvas, sentiment, convergence, picks)
    data/reports/<date>/    LOAD     — email HTML + artifact HTML
    data/curated/etl_runs/  manifest — one JSON per run (stage status, timing, row counts, lineage)

Stages
    E1 extract_universe       validate/snapshot the ticker universes
    E2 extract_market_scans   ensure a fresh scan workbook exists per market (reuse today's, else note)
    E3 extract_news           pull market-mood + per-pick headlines via the RSS providers
    T1 transform_fundamentals scan workbook -> curated fundamentals parquet (+ PE zone)
    T2 transform_darvas       scan workbook -> curated darvas parquet (fresh-breakout flags)
    T3 transform_sentiment    news -> curated per-ticker sentiment parquet
    T4 transform_convergence  fundamentals x sentiment -> curated convergence parquet
    L1 load_report            build the email HTML + Artifact page (delegates to build_email.py)
    L2 load_manifest          write the run manifest (lineage + row counts + status)

CLI
    python3 etl_pipeline.py --phase all               # E -> T -> L
    python3 etl_pipeline.py --phase T,L               # skip extract, reuse today's raw
    python3 etl_pipeline.py --stage transform_darvas  # a single stage
    python3 etl_pipeline.py --markets US,EU --force    # ignore idempotency
    python3 etl_pipeline.py --dry-run                  # print the plan only
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd

BASE = os.path.expanduser("~/Downloads/code/python_files")
RUN_DATE = date.today().isoformat()
RAW = os.path.join(BASE, "data", "raw", RUN_DATE)
CURATED = os.path.join(BASE, "data", "curated")
REPORTS = os.path.join(BASE, "data", "reports", RUN_DATE)
RUNS = os.path.join(CURATED, "etl_runs")
for d in (RAW, CURATED, REPORTS, RUNS):
    os.makedirs(d, exist_ok=True)

# Where each market's scan workbook lives (the EXTRACT product we curate from).
SCAN_GLOBS = {
    "US": "us_full_scan/us_full_scan_*.xlsx",
    "EU": "european_scan/european_market_scan_broad_*.xlsx",
    "IN": "indian_full_scan/indian_full_scan_*.xlsx",
}
FUND_SHEET = {
    "US": "All_Fundamentals",
    "EU": "Fundamentals",
    "IN": None,
}  # IN scan carries no fundamentals


def _latest(patt):
    files = sorted(glob.glob(os.path.join(BASE, patt)), key=os.path.getmtime)
    return files[-1] if files else None


# ────────────────────────────── stage framework ──────────────────────────────
class Ctx:
    """Carries artifacts + lineage between stages within one run."""

    def __init__(self, markets, force, no_send=False):
        self.markets = markets
        self.force = force
        self.no_send = no_send
        self.artifacts = {}  # logical name -> path
        self.rows = {}  # logical name -> row count
        self.lineage = {}  # output -> [inputs]
        self.status = {}  # stage -> ok|skip|fail|dry
        self.timings = {}  # stage -> seconds
        self.notes = {}  # stage -> message

    def fresh(self, path):
        """Idempotency: an output is fresh if it exists and was written today."""
        if self.force or not path or not os.path.exists(path):
            return False
        return datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat() == RUN_DATE


STAGES = []  # (name, phase, fn)


def stage(name, phase):
    def deco(fn):
        STAGES.append((name, phase, fn))
        return fn

    return deco


# ─────────────────────────────── EXTRACT ───────────────────────────────
@stage("extract_universe", "E")
def extract_universe(ctx):
    """Snapshot + sanity-check the ticker universes feeding the scans."""
    out = os.path.join(RAW, "universe_manifest.json")
    if ctx.fresh(out):
        ctx.artifacts["universe"] = out
        return "skip"
    manifest = {}
    for name, patt in [
        ("europe_broad", "data/europe_broad_list.csv"),
        ("global_master", "data/global_universe_master.csv"),
    ]:
        p = os.path.join(BASE, patt)
        if os.path.exists(p):
            n = sum(1 for _ in open(p)) - 1
            manifest[name] = {"path": patt, "tickers": n}
            ctx.rows[f"universe:{name}"] = n
    json.dump(manifest, open(out, "w"), indent=2)
    ctx.artifacts["universe"] = out
    ctx.lineage[out] = [m["path"] for m in manifest.values()]
    return "ok"


@stage("extract_market_scans", "E")
def extract_market_scans(ctx):
    """Locate each market's scan workbook (the raw OHLC+fundamentals extract).
    We reuse today's workbook if present; a full re-scan is a heavy job left to
    the scan scripts (full_european_market_scan.py etc.) and is only *flagged*
    as stale here, never silently skipped."""
    stale = []
    for m in ctx.markets:
        patt = SCAN_GLOBS.get(m)
        wb = _latest(patt) if patt else None
        if not wb:
            ctx.notes.setdefault("extract_market_scans", []).append(f"{m}: NO scan workbook found")
            continue
        fresh = datetime.fromtimestamp(os.path.getmtime(wb)).date().isoformat() == RUN_DATE
        if not fresh:
            stale.append(f"{m}:{os.path.basename(wb)}")
        ctx.artifacts[f"scan:{m}"] = wb
    if stale:
        ctx.notes.setdefault("extract_market_scans", []).append(
            "stale (not today) — re-run the scan script to refresh: " + ", ".join(stale)
        )
    return "ok"


@stage("extract_news", "E")
def extract_news(ctx):
    """Pull market-mood headlines via the free RSS providers, land as json."""
    out = os.path.join(RAW, "news_mood.json")
    if ctx.fresh(out):
        ctx.artifacts["news"] = out
        return "skip"
    try:
        from sentiment_pipeline import SentimentPipeline

        sp = SentimentPipeline()
        mood = {m: (sp.get_market_mood(m) or {}) for m in ctx.markets}
    except Exception as e:  # pragma: no cover - provider/network variance
        ctx.notes["extract_news"] = f"sentiment unavailable: {str(e)[:80]}"
        mood = {}
    json.dump(mood, open(out, "w"), indent=2, default=str)
    ctx.artifacts["news"] = out
    for m, d in mood.items():
        ctx.rows[f"news:{m}"] = d.get("n_articles", 0)
    return "ok"


# ─────────────────────────────── TRANSFORM ───────────────────────────────
def _pe_zone(pe, sm):
    if pd.isna(pe) or pe <= 0 or pd.isna(sm) or sm <= 0:
        return "n/a"
    r = pe / sm
    return "BUY" if r <= 0.8 else "FAIR" if r <= 1.1 else "CAUTION" if r <= 1.6 else "RICH"


@stage("transform_fundamentals", "T")
def transform_fundamentals(ctx):
    """Scan workbook fundamentals -> normalized parquet with a sector-relative PE zone."""
    frames = []
    for m in ctx.markets:
        wb = ctx.artifacts.get(f"scan:{m}")
        sheet = FUND_SHEET.get(m)
        if not wb or not sheet:
            continue
        df = pd.read_excel(wb, sheet_name=sheet)
        pe_col = "P_E_Ratio" if "P_E_Ratio" in df.columns else None
        if pe_col is None and "Earnings_Yield_%" in df.columns:
            df["P_E_Ratio"] = df["Earnings_Yield_%"].apply(
                lambda e: 100.0 / e if pd.notna(e) and e > 0 else np.nan
            )
            pe_col = "P_E_Ratio"
        df["P_E_Ratio"] = pd.to_numeric(df.get(pe_col), errors="coerce")
        med = df.groupby("Sector")["P_E_Ratio"].transform("median")
        df["PE_Zone"] = [_pe_zone(pe, sm) for pe, sm in zip(df["P_E_Ratio"], med)]
        df["Market"] = m
        keep = [
            c
            for c in [
                "Market",
                "Symbol",
                "Name",
                "Sector",
                "LTP",
                "P_E_Ratio",
                "PE_Zone",
                "Piotroski_Score",
                "CoffeeCan_Class",
                "Darvas_Signal",
            ]
            if c in df.columns
        ]
        frames.append(df[keep])
    if not frames:
        return "skip"
    out = os.path.join(CURATED, "fundamentals.parquet")
    allf = pd.concat(frames, ignore_index=True)
    allf.to_parquet(out, index=False)
    ctx.artifacts["fundamentals"] = out
    ctx.rows["fundamentals"] = len(allf)
    ctx.lineage[out] = [
        ctx.artifacts.get(f"scan:{m}") for m in ctx.markets if f"scan:{m}" in ctx.artifacts
    ]
    return "ok"


@stage("transform_darvas", "T")
def transform_darvas(ctx):
    """Scan workbook Darvas signals -> normalized parquet, flagging fresh breakouts."""
    frames = []
    for m in ctx.markets:
        wb = ctx.artifacts.get(f"scan:{m}")
        if not wb:
            continue
        try:
            df = pd.read_excel(wb, sheet_name="Darvas_Signals")
        except Exception:
            continue
        pos = pd.to_numeric(df.get("Position_in_Box%"), errors="coerce")
        chg = pd.to_numeric(df.get("Change%"), errors="coerce")
        df["fresh_breakout"] = (
            (df.get("Darvas_Signal") == "BREAKOUT_BUY") & pos.between(100, 120) & (chg > 0)
        )
        df["Market"] = m
        keep = [
            c
            for c in [
                "Market",
                "Symbol",
                "Name",
                "LTP",
                "Change%",
                "Darvas_Signal",
                "Box_Top",
                "Position_in_Box%",
                "fresh_breakout",
            ]
            if c in df.columns
        ]
        frames.append(df[keep])
    if not frames:
        return "skip"
    out = os.path.join(CURATED, "darvas.parquet")
    allf = pd.concat(frames, ignore_index=True)
    allf.to_parquet(out, index=False)
    ctx.artifacts["darvas"] = out
    ctx.rows["darvas"] = len(allf)
    ctx.rows["darvas:fresh"] = int(allf["fresh_breakout"].sum())
    return "ok"


@stage("transform_sentiment", "T")
def transform_sentiment(ctx):
    """Score per-pick news sentiment for the strongest fundamental names."""
    fund = ctx.artifacts.get("fundamentals")
    if not fund:
        return "skip"
    try:
        from sentiment_pipeline import SentimentPipeline

        sp = SentimentPipeline()
    except Exception as e:
        ctx.notes["transform_sentiment"] = f"unavailable: {str(e)[:80]}"
        return "fail"
    picks = pd.read_parquet(fund)
    rows = []
    for m in ctx.markets:
        sub = picks[
            (picks["Market"] == m)
            & (pd.to_numeric(picks.get("Piotroski_Score"), errors="coerce") >= 7)
        ]
        seen = set()
        for _, r in sub.head(40).iterrows():
            nm = str(r.get("Name") or r["Symbol"])
            if nm.upper() in seen:
                continue
            seen.add(nm.upper())
            s = (
                sp.get_ticker_sentiment(r["Symbol"], m, company_name=nm)
                if m == "EU"
                else sp.get_ticker_sentiment(r["Symbol"], m)
            )
            if s.n_articles > 0 and s.label != "NO_DATA":
                rows.append(
                    {
                        "Market": m,
                        "Symbol": r["Symbol"],
                        "Name": nm,
                        "sentiment": s.label,
                        "score": s.score,
                        "n_articles": s.n_articles,
                        "headline": (s.top_headlines[0]["title"] if s.top_headlines else ""),
                    }
                )
    out = os.path.join(CURATED, "sentiment.parquet")
    pd.DataFrame(rows).to_parquet(out, index=False)
    ctx.artifacts["sentiment"] = out
    ctx.rows["sentiment"] = len(rows)
    return "ok"


@stage("transform_convergence", "T")
def transform_convergence(ctx):
    """Join fundamentals (strong) x sentiment -> convergence table."""
    fund, sent = ctx.artifacts.get("fundamentals"), ctx.artifacts.get("sentiment")
    if not fund or not sent:
        return "skip"
    f = pd.read_parquet(fund)
    s = pd.read_parquet(sent)
    if s.empty:
        out = os.path.join(CURATED, "convergence.parquet")
        s.to_parquet(out, index=False)
        ctx.artifacts["convergence"] = out
        ctx.rows["convergence"] = 0
        return "ok"
    strong = f[pd.to_numeric(f.get("Piotroski_Score"), errors="coerce") >= 7][
        ["Market", "Symbol", "Sector", "PE_Zone"]
    ]
    conv = s.merge(strong, on=["Market", "Symbol"], how="inner")
    conv["signal"] = np.where(
        conv["sentiment"] == "POSITIVE",
        "HIGH_CONVICTION",
        np.where(conv["sentiment"] == "NEGATIVE", "CAUTION", "MIXED"),
    )
    out = os.path.join(CURATED, "convergence.parquet")
    conv.to_parquet(out, index=False)
    ctx.artifacts["convergence"] = out
    ctx.rows["convergence"] = len(conv)
    ctx.lineage[out] = [fund, sent]
    return "ok"


# ─────────────────────────────── LOAD ───────────────────────────────
@stage("load_report", "L")
def load_report(ctx):
    """Build the email HTML + Artifact page from the curated data (delegates to build_email.py)."""
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "build_email.py")],
        capture_output=True,
        text=True,
        cwd=BASE,
    )
    line = next((l for l in r.stdout.splitlines() if l.startswith("SUBJECT:")), "")
    ctx.notes["load_report"] = line or (r.stderr.splitlines()[-1] if r.stderr else "no output")
    for name, src in [
        ("email", "daily_market_report_%s.html" % RUN_DATE),
        ("artifact", "daily_market_report_artifact.html"),
    ]:
        p = os.path.expanduser(f"~/Downloads/{src}")
        if os.path.exists(p):
            ctx.artifacts[name] = p
    return "ok" if r.returncode == 0 else "fail"


@stage("load_deliver", "L")
def load_deliver(ctx):
    """Email the report token-free via send_mailer.send (Gmail SMTP). Skips when
    --no-send is set or no GMAIL_USER/GMAIL_APP_PASSWORD is configured (report is
    still saved to ~/Downloads either way)."""
    report = ctx.artifacts.get("email")
    if not report or not os.path.exists(report):
        return "skip"
    if ctx.no_send:
        ctx.notes["load_deliver"] = "--no-send: report saved, not emailed"
        return "skip"
    pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not os.environ.get("GMAIL_USER") or len(pw) < 12 or "PUT-YOUR" in pw.upper():
        ctx.notes["load_deliver"] = (
            "no valid GMAIL_APP_PASSWORD (placeholder?) — report saved, not emailed"
        )
        return "skip"
    subject = ctx.notes.get("load_report", "").replace("SUBJECT: ", "").strip() or (
        f"Daily Market Report — {RUN_DATE}"
    )
    try:
        import send_mailer

        ok = send_mailer.send(subject, "See the HTML report.", open(report).read())
        ctx.notes["load_deliver"] = (
            "emailed" if ok else "send returned False"
        ) + f": {subject[:60]}"
        return "ok" if ok else "fail"
    except Exception as e:
        ctx.notes["load_deliver"] = f"send failed: {str(e)[:80]}"
        return "fail"


@stage("load_manifest", "L")
def load_manifest(ctx):
    """Write the run manifest — status, timings, row counts, lineage."""
    out = os.path.join(RUNS, f"run_{RUN_DATE}.json")
    manifest = {
        "run_date": RUN_DATE,
        "generated": datetime.now().isoformat(),
        "markets": ctx.markets,
        "forced": ctx.force,
        "stage_status": ctx.status,
        "stage_seconds": {k: round(v, 2) for k, v in ctx.timings.items()},
        "row_counts": ctx.rows,
        "notes": ctx.notes,
        "artifacts": {k: os.path.relpath(v, BASE) for k, v in ctx.artifacts.items() if v},
        "lineage": {
            os.path.relpath(k, BASE): [os.path.relpath(i, BASE) for i in v if i]
            for k, v in ctx.lineage.items()
        },
    }
    json.dump(manifest, open(out, "w"), indent=2)
    ctx.artifacts["manifest"] = out
    return "ok"


# ─────────────────────────────── runner ───────────────────────────────
def run(markets, phases, only_stage, force, dry, no_send=False):
    ctx = Ctx(markets, force, no_send=no_send)
    print(
        f"ETL run {RUN_DATE} | markets={','.join(markets)} | phases={','.join(phases)}"
        f"{' | STAGE='+only_stage if only_stage else ''}{' | FORCE' if force else ''}{' | DRY-RUN' if dry else ''}"
    )
    for name, phase, fn in STAGES:
        if only_stage and name != only_stage:
            continue
        if phase not in phases and not only_stage:
            continue
        if dry:
            print(f"  [{phase}] {name} … (dry)")
            ctx.status[name] = "dry"
            continue
        t0 = time.time()
        try:
            st = fn(ctx) or "ok"
        except Exception as e:
            st = "fail"
            ctx.notes[name] = f"EXC {type(e).__name__}: {str(e)[:120]}"
        ctx.timings[name] = time.time() - t0
        ctx.status[name] = st
        extra = ""
        {k: v for k, v in ctx.rows.items() if k == name or k.startswith(name.split("_")[-1])}
        if name in (
            "transform_fundamentals",
            "transform_darvas",
            "transform_sentiment",
            "transform_convergence",
        ):
            key = name.split("transform_")[-1]
            if key in ctx.rows:
                extra = f" · {ctx.rows[key]} rows"
        note = ctx.notes.get(name)
        note = ("; ".join(note) if isinstance(note, list) else note) if note else ""
        print(
            f"  [{phase}] {name:26} {st:5}{extra} ({ctx.timings[name]:.1f}s)"
            + (f"  ⚠ {note}" if note and st != "ok" else (f"  · {note}" if note else ""))
        )
    # always finalize the manifest unless we ran a single non-manifest stage
    if not dry and (not only_stage or only_stage == "load_manifest"):
        if "load_manifest" not in ctx.status:
            load_manifest(ctx)
    return ctx


def main():
    ap = argparse.ArgumentParser(description="ETL pipeline for the daily multi-market report")
    ap.add_argument("--markets", default="US,EU,IN", help="comma list: US,EU,IN")
    ap.add_argument("--phase", default="all", help="all or comma subset of E,T,L")
    ap.add_argument("--stage", default=None, help="run a single stage by name")
    ap.add_argument("--force", action="store_true", help="ignore idempotency / re-run")
    ap.add_argument(
        "--no-send", action="store_true", help="build/save the report but do not email it"
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    phases = (
        ["E", "T", "L"]
        if args.phase == "all"
        else [p.strip().upper() for p in args.phase.split(",")]
    )
    markets = [m.strip().upper() for m in args.markets.split(",")]
    ctx = run(markets, phases, args.stage, args.force, args.dry_run, no_send=args.no_send)
    man = ctx.artifacts.get("manifest")
    if man:
        print(f"\nmanifest → {os.path.relpath(man, BASE)}")


if __name__ == "__main__":
    main()
