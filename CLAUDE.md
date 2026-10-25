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

<!-- source-fetch-toolkit:v1 (managed by ~/bin/add_source_fetch_section.py — edit there, not here) -->
## Source fetching for data collection & literature surveys

When a task needs a primary document (statute, regulator data, government release, paper, filing),
fetch the document itself — never cite a search snippet as if it had been read.

- **On the owner's Mac:** `fetch_source.py "<url | doi:… | celex:… | arxiv:…>" --out ./sources`
  (in `~/bin`; full guide `~/bin/SOURCE_FETCH_TOOLKIT.md`). Scheduled/unattended runs use only
  `bash /Users/umashankar/bin/fetch_source.sh "<target>"` (allowlisted) and then Read the `.txt` it reports.
- **Elsewhere (cloud sessions, CI):** follow the same ladder by hand — direct GET with a browser User-Agent →
  headless browser only if the page needs JavaScript → official alternates (DOI → OpenAlex
  `api.openalex.org/works/doi:<doi>` locations → repository copy; EUR-Lex → EU Publications Office
  `publications.europa.eu/resource/celex/<CELEX>`; arXiv pdf/abs) → Wayback Machine `id_` snapshot.
- **Hard rule:** a CAPTCHA, robot check, Cloudflare/Akamai/WAF challenge or login wall means stop on that
  host. Do not bypass it (no TLS impersonation, stealth browsers, identity rotation or challenge solving);
  look for the same document via another route, or report it as unavailable.
- **Record** for every figure: URL read, title/date, page/table, fetch route; mark abstract-only or
  snippet-only sources. Fetch politely (~1 request/second per host, no bulk crawling).
<!-- /source-fetch-toolkit -->
