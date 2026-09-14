# CLAUDE.md — global-stock-screener

## What this repo is

A 20-market equity screener that **ships with ~1 year of cached price data** (~40,000 symbols
across the world's major exchanges) — clone and get screening results in minutes, no API keys,
no LLM tokens. Sibling repo to [`global-market-data`](https://github.com/herrrickshaw/global-market-data),
which does the same strategy library over a deeper 10-year point-in-time history for backtesting;
this repo is for *today's* screen results.

> ⚠️ Educational / research only. NOT investment advice. Screener output is a mechanical filter,
> not a buy/sell signal.

## Run

```bash
git lfs install && git clone https://github.com/herrrickshaw/global-stock-screener.git
cd global-stock-screener && git lfs pull
pip install -r requirements.txt
python run.py                         # global momentum leaderboard
python run.py --strategy garp --market US --top 25
python run.py --brief                 # full Daily Market Brief → results/daily_brief.html
python run.py --list                  # all strategies & markets
python preflight.py --ensure          # verify/establish LFS data + packages + serving views
```

`run.py` auto-bootstraps the cached data into a fast local store on first use.

## Key docs (read before assuming, don't duplicate here)

| Doc | What |
|---|---|
| `DATA_AND_MODULES.md` | module map, what each script does |
| `ARCHITECTURE.md` | system design |
| `DATA_SOURCES.md` / `EXCHANGE_COVERAGE.md` | where data comes from, per-market coverage |
| `DATA_VALIDATION_GUIDE.md` | data quality checks |
| `AUTO_SCREENER.md` | the mailer/automation path |

Before enabling or modifying any schedule around `send_mailer.py`, confirm it still has a
duplicate-send guard (or that callers audit per-day send-count before invoking `--send`) —
a mailer without one is a recurring footgun elsewhere in this account's pipelines.

## Cross-session project memory

A Claude Code session rooted here has no persisted memory of its own. Decisions, hazards, and
credential locations for the broader market-research platform (of which this screener is one
project — see `project_bhavcopy_phase1`-successor and `project_systematic_strategy_platform` in
that memory) live under the `~` (home) session instead: `~/.claude/projects/-Users-umashankar/memory/`,
indexed by `MEMORY.md` and mapped by the `reference_memory_map` memory. From here, reach it with
`qmd search "<topic>"` (indexes that memory directory regardless of working directory) rather than
assuming this session has its own history. For fast orientation, a published snapshot of 128
incident-sourced rules from across that memory is browsable at
https://claude.ai/code/artifact/e29ceaeb-099e-4de7-ab43-dcd97a2d8f57 ("Ways of Working") — a
starting point, not authoritative over the live memory files.
