# WarEra Ireland tools

WarEra Ireland tools for The Emerald Accord alliance in WarEra: battle damage and bounty, company taxes, money transfers and donations,
player efficiency, and plain-English questions over the data. A collector in a private repo reads the WarEra API
(`api2.warera.io`) every hour and publishes `site/data.json` here; the pages read that file.

## Apps

| Page | What it shows |
|---|---|
| `site/index.html` **WarEra Tracker** | Battle damage and battle money (bounty) by alliance, country, military unit and player; per-country bar chart; bounty per 1M damage, with a day-by-day chart, a player card with a drill-down to each battle, and a three-player comparison. |
| `site/company.html` **Company tax tracker** | Pick a host (any Emerald Accord country) and a source country (any owner citizenship, or All owners): tax collected per hour on those companies, the daily and monthly amount owed, a cross-check against the game's region figures, and at the end the host country's whole income per day by stream (employee and manager income tax, development, strategic resources, government type, and an estimate of market tax), with the last 30 days day by day. |
| `site/transfers.html` **EA Money Transfers** | Tab 1: country money transfers between alliance nations (totals, battles per nation, sortable list). Tab 2: citizens' donations to their own nation (totals, nation, citizen and amount filters, sortable tables, donations per day). |
| `site/efficiency.html` **Player efficiency** | The alliance's top 100 players (country filter) with at least 5M damage (slider) in the last 7 days, ranked by wealth gained (or wealth) per 1M damage, with their build: War (20% or less of skill points in companies, energy, management and production), Eco (over 50%) or Hybrid. Tap a player for skills and daily trend charts. |
| `site/status.html` **Status** | Health checks, the last refresh and its stage timings, recent runs, last backup and digest, stored history. |
| `site/guide.html` **Guide** | For alliance members: what each app shows, how its figures are worked out, data limits, alerts, glossary. |
| `site/ask.html` **Ask WarEra** | Questions in plain English answered as tables; runs inside Claude (artifact runtime). Hidden outside testing mode. |

Every page shows an amber banner when its data is more than 2 hours old. Tables have a CSV download and, on phones, a cards or table layout.
Testing mode (shows hidden pages): tap the footer line 5 times.

## Where the pages run
- **Streamlit**: `streamlit_app.py` serves every page with `data.json` inlined (deploy on Streamlit Community Cloud). Ask WarEra is hidden unless the app is opened with `?key=<DEV_KEY>` (`DEV_KEY` in the app's Secrets).
- **Claude artifacts**: `python3 scripts/sync_artifacts.py OUT_DIR` builds the Tracker artifact (all pages but Ask) and the Ask WarEra artifact from `site/`; hourly scheduled tasks run it and publish, so the copies cannot drift from the repo.

## Set up
1. This repo **Settings → Secrets and variables → Actions**: secrets `WARERA_API_KEY` and `ALERT_WEBHOOK_URL` (for the battle check).
2. **Settings → Actions → General → Workflow permissions: Read and write** (the battle check saves its state branch).
3. On https://share.streamlit.io choose **Create app**, this repo, branch `main`, file `streamlit_app.py`. Secrets there: `DEV_KEY`
   (unlocks Ask and Settings), `GITHUB_TOKEN` (fine-grained, Contents read and write on the private back-end repo, so the Settings
   page can save the tax agreements).

The API key and webhook are GitHub secrets only. Run the Streamlit app locally with `uv run streamlit run streamlit_app.py`.

## How it is split
This repo is **public**: the pages (`site/`), the Streamlit app, the 15-minute battle check and the data files the pages read.
The collector, the history database and its backups, the tax agreements and the statements live in the **private** repo
`nottheragingdemon/WarEraTracker-backend`. Every hour it collects, exports and pushes `site/data.json`, `site/ask-data.json`
and `site/company-data.json` here (the "data: …" commits); Streamlit redeploys on those pushes.

## Data
- `site/data.json` is the core data (about 0.7 MB); `site/battle-data.json` (per-battle stats) is loaded by the Battles page and Ask, `site/transfer-data.json` (donor lists) by the Transfers page, `site/ask-data.json` (bounty history, contracts) by Ask only, `site/company-data.json` (tracked companies, wage history) by the Company page and Ask. Pages load the parts with `weLoad()`; the Streamlit app inlines them.
- `site/contract.json` is the agreement with the back end: the data `schema` number, the keys `data.json` must have, and the parts that must be non-empty. The back end checks it before publishing; the Battle check also warns when data is missing, empty or older than 3 hours.
- History is kept for 90 days in the back end (frozen tax statements permanently). The Company tax tracker covers the companies under Ireland's tax agreements (Mexico in Ireland's core regions, the United Kingdom in Northern Ireland).

## Workflows (this repo)
| Workflow | When | What |
|---|---|---|
| Battle check | every 15 minutes | new and ended battles involving the alliance to the webhook (`scripts/battlecheck.py`; already-announced marks on the `battlecheck-state` branch; switches: test alert, test failure); also warns when the site data is more than 3 hours old or missing/empty (once per outage) |
| Live app check | every 6 hours | is the Streamlit app up (`scripts/live_check.py`; a sleeping app is fine); a failure posts to the webhook. Optional variable `STREAMLIT_URL` |
| Tests | on push | page, Streamlit and artifact tests, then every page in headless Chrome (`scripts/smoke_pages.py`), once as plain files and once as the Streamlit app serves them (`--streamlit`), checking real numbers are on screen |
| Release | by hand | tags a version from `CHANGELOG.md` and publishes a GitHub release |

The hourly refresh, company index, backups, weekly digest, statements and their workflows are in the back-end repo.

## Alerts
With `ALERT_WEBHOOK_URL` set: new battles involving the alliance, battles that ended (won or lost, damage per side, link), the weekly digest
(this week against last week, top countries and players, bounty per 1M damage, player efficiency, transfers and donations),
a warning with a link when a workflow run fails, a note when collector stages are skipped after API errors (at most every 6 hours), and a stale-data warning when any kind of data stops arriving as often as it should (checked every hour by the back end). New and ended battles come from the 15-minute battle check in this repo; everything else from the hourly back end.
Money alerts: a transfer between alliance nations of at least `ALERT_TRANSFER_MIN` (default 5,000), a citizen giving their own nation at least `ALERT_DONATION_DAY_MIN` in one day (default 5,000; single donations are capped at 200), and a treasury falling by at least `ALERT_TREASURY_DROP_MIN` (default 5,000) and by half within 24 hours. Change the defaults with repository variables of the same names.
The first run of each alert type only records a baseline.

## Backups and recovery
The history database and its weekly backups are in the back-end repo (`state` and `backup/state-*` branches there). A released version of the pages can be checked out by its tag (see `CHANGELOG.md`).

## Tests
`python -m unittest discover -s tests` (the Company page in headless Chrome, the Streamlit app, the artifact copies, the data contract) and `python3 scripts/smoke_pages.py [--streamlit]`. The collector's tests are in the back-end repo.
