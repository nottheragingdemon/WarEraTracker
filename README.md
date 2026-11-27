# WarEra Tracker

Tools for The Emerald Accord alliance in WarEra: battle damage and bounty, company taxes, money transfers and donations,
player efficiency, and plain-English questions over the data. A collector on GitHub Actions reads the WarEra API
(`api2.warera.io`) every hour and writes `site/data.json`; the pages read that file.

## Apps

| Page | What it shows |
|---|---|
| `site/index.html` **WarEra Tracker** | Battle damage and battle money (bounty) by alliance, country, military unit and player; per-country bar chart; bounty per 1M damage, with a day-by-day chart, a player card with a drill-down to each battle, and a three-player comparison. |
| `site/company.html` **Company tax tracker** | Pick a host and a source country: tax collected per hour on those companies, the daily and monthly amount owed, a cross-check against the game's region figures, and at the end the host country's whole income per day by stream (employee and manager income tax, development, strategic resources, government type, and an estimate of market tax), with the last 30 days day by day. |
| `site/transfers.html` **EA Money Transfers** | Tab 1: country money transfers between alliance nations (totals, battles per nation, sortable list). Tab 2: citizens' donations to their own nation (totals, nation, citizen and amount filters, sortable tables, donations per day). |
| `site/efficiency.html` **Player efficiency** | Per nation, the top 20 players with 1M+ damage in the last 7 days, ranked by wealth gained (or wealth) per 1M damage, with their build: War (20% or less of skill points in companies, energy, management and production), Eco (over 50%) or Hybrid. Tap a player for skills and daily trend charts. |
| `site/status.html` **Status** | Health checks, the last refresh and its stage timings, recent runs, last backup and digest, stored history. |
| `site/ask.html` **Ask WarEra** | Questions in plain English answered as tables; runs inside Claude (artifact runtime). Hidden outside testing mode. |

Every page shows an amber banner when its data is more than 2 hours old. Tables have a CSV download and, on phones, a cards or table layout.
Testing mode (shows hidden pages): tap the footer line 5 times.

## Where the pages run
- **Streamlit**: `streamlit_app.py` serves every page with `data.json` inlined (deploy on Streamlit Community Cloud). Ask WarEra is hidden unless the app is opened with `?key=<DEV_KEY>` (`DEV_KEY` in the app's Secrets).
- **Claude artifacts**: `python3 scripts/sync_artifacts.py OUT_DIR` builds the Tracker artifact (all pages but Ask) and the Ask WarEra artifact from `site/`; hourly scheduled tasks run it and publish, so the copies cannot drift from the repo.

## Set up
1. Repo **Settings → Secrets and variables → Actions**: secret `WARERA_API_KEY` (your API key); optional secret `ALERT_WEBHOOK_URL` (a Discord or Slack webhook).
2. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
3. **Actions → Refresh data → Run workflow** once.
4. On https://share.streamlit.io choose **Create app**, this repo, branch `main`, file `streamlit_app.py`.

The API key is never stored in the repo. The repo is public, so the `state` branch (the collected game data) is public too.
Run locally: `WARERA_API_KEY=... sh refresh.sh`, then `uv run streamlit run streamlit_app.py`.

## Data
- `wartrack/` is the collector and exporter: Python standard library plus `AsyncHTTPClient` from [async-http-kit](https://github.com/nottheragingdemon/async-http-kit) (`asynchttp.aio`, on aiohttp) for many requests at once; urllib is the fallback. Collector dependencies are pinned in `requirements-collector.txt`. `scope.json` limits collection to The Emerald Accord's battles since 2026-11-10.
- History lives in a SQLite database kept on the `state` branch (one force-pushed commit). Data older than 90 days is pruned (`WARTRACK_KEEP_DAYS`); bounty snapshots older than a week keep one per day.
- `site/data.json` is the core data (per-battle stats packed, about 2 MB); `site/ask-data.json` (bounty history, contracts) is loaded by Ask WarEra only.
- Transfers and donations are kept for 90 days. Player efficiency takes one snapshot of wealth and total damage per player per UTC day, for each nation's top 100 players by this week's damage, and refreshes skills daily or after a reset (a level-L skill costs 1+2+…+L points).
- Market trades (`trading` transactions) the game lists under each alliance country (its citizens buying or selling) are kept 30 days to estimate market tax: the country's market tax rate × the average daily value of those trades over the last 7 full days. The game doesn't report market tax, and which side's country collects it isn't published.
- Country income (treasury and income by stream) is stored hourly for the alliance's countries; the Company tax tracker shows it day by day.
- The MU list is refreshed every 6 hours (`WARTRACK_PEOPLE_EVERY_H`) and closed mercenary contracts every 3 hours (`WARTRACK_CONTRACTS_FULL_H`).
- The community cache `gateway.warerastats.io` can be used first by setting the repository variable `WARERA_GATEWAY=1` (or the *gateway* switch on a manual run). It is off by default: in November 2026 it was slower than the official API and returned backend errors in every run.

## Workflows
| Workflow | When | What |
|---|---|---|
| Refresh data | hourly at :17 | collect, export `data.json`, battle alerts, save the database |
| Quick sample | every 15 minutes | region tax rates and new or ended battles, then battle alerts (switches: test alert, test failure) |
| Weekly digest | Mondays 08:23 UTC | the week's summary to the webhook (`python -m wartrack alerts --print-digest` shows it without sending) |
| Weekly backup | Sundays 03:07 UTC | copies the database to `backup/state-YYYY-MM-DD`, keeping the newest 4 |
| Tests | on push | unit tests, then every page in headless Chrome (`scripts/smoke_pages.py`) |
| Release | by hand | tags a version from `CHANGELOG.md` and publishes a GitHub release |

## Alerts
With `ALERT_WEBHOOK_URL` set: new battles involving the alliance, battles that ended (won or lost, damage per side, link), the weekly digest
(this week against last week, top countries and players, bounty per 1M damage, player efficiency, transfers and donations),
a warning with a link when a workflow run fails, and a note when collector stages are skipped after API errors (at most every 6 hours).
Money alerts: a transfer between alliance nations of at least `ALERT_TRANSFER_MIN` (default 5,000), a citizen giving their own nation at least `ALERT_DONATION_DAY_MIN` in one day (default 5,000; single donations are capped at 200), and a treasury falling by at least `ALERT_TREASURY_DROP_MIN` (default 5,000) and by half within 24 hours. Change the defaults with repository variables of the same names.
The first run of each alert type only records a baseline.

## Backups and recovery
`sh state.sh restore` takes the `state` branch, or the newest backup if `state` is missing or damaged; `sh state.sh save` refuses
to store a damaged or emptied database; `sh state.sh backup` makes a dated copy. A released version can be checked out by its tag (see `CHANGELOG.md`).

## Tests
`python -m unittest discover -s tests` (offline: API client against a fake server, digest, pruning, donations backfill, player efficiency, artifact sync) and `python3 scripts/smoke_pages.py`.
