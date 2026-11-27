# WarEra Tracker

Dashboard for WarEra battle damage, orders, bounty, contracts and citizens' company locations/taxes,
filterable by alliance, country, MU and player. Data comes from `api2.warera.io`. The community cache at `gateway.warerastats.io` can be used first (same API key) by setting the repository variable `WARERA_GATEWAY=1`, or for one manual run with the *gateway* switch; it is off by default because in November 2026 it was slower than the official API and returned backend errors in every run.

- `streamlit_app.py` serves `site/index.html` with `site/data.json` inlined (deploy on Streamlit Community Cloud).
- `.github/workflows/refresh.yml` runs hourly: restores the history database from the `state` branch, collects new data,
  rebuilds `site/data.json`, saves the database back to `state` (one force-pushed commit) and commits `data.json`.
- `wartrack/` is the collector/exporter (standard library plus `aiohttp`: requests go through `wartrack/async_requests.py`, several in flight at once; falls back to urllib if aiohttp is missing). `scope.json` limits collection to The Emerald Accord's battles since 2026-11-10.

## Set up
1. Repo **Settings → Secrets and variables → Actions → New repository secret**: `WARERA_API_KEY` = your API key.
2. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
3. **Actions → Refresh data → Run workflow** once.
4. On https://share.streamlit.io choose **Create app**, pick this repo, branch `main`, file `streamlit_app.py`.

The API key is never stored in the repo. This repo is public, so the `state` branch (the collected game data) is public too.

Run locally: `WARERA_API_KEY=... sh refresh.sh` then `uv run streamlit run streamlit_app.py`.

## Apps
`site/index.html` (WarEra Tracker), `site/company.html` (Company tax tracker: pick a host country and a source country; per-hour tax, daily and monthly owed, staff cross-check and day-by-day table) and `site/ask.html` (Ask WarEra: plain-English questions answered as tables; needs Claude's artifact runtime). `streamlit_app.py` serves the first two with navigation.

## Alerts (optional)
Add a repository secret `ALERT_WEBHOOK_URL` (a Discord or Slack incoming webhook). Each hourly refresh then posts new battles involving the tracked alliance's countries. The first run only records a baseline.

## Tax sampling
`.github/workflows/tax-sample.yml` records region tax rates every 15 minutes (one public API call), so tax history is finer than the hourly refresh. The page shows a warning when `data.json` is more than 3 hours old.

## Tests and failure alerts
- `python -m unittest discover -s tests` runs offline tests of the API client against a local fake server (also run by the *Tests* workflow).
- If `ALERT_WEBHOOK_URL` is set, a failed workflow run posts a warning with a link to the run, and collector stages skipped after API errors are reported at most once every 6 hours.
- Every page shows an amber banner when its data is more than 2 hours old.

## Weekly digest and artifact copies
- The *Weekly digest* workflow (Mondays 08:23 UTC, or run it by hand) posts the week's battles, top countries by damage, top bounty per 1M damage (countries and players), money transfers and citizen donations to `ALERT_WEBHOOK_URL`. `python -m wartrack alerts --print-digest` shows the text without sending it.
- `python3 scripts/sync_artifacts.py OUT_DIR` builds the two Claude-artifact copies (Tracker, Ask WarEra) from `site/`; the hourly republish tasks run it, so the copies cannot drift from the repo.
- `site/data.json` is the core data; `site/ask-data.json` (bounty history and contracts) is loaded by Ask WarEra only.
- Battle alerts also report when an alliance battle ends (won / lost, damage per side). The weekly digest opens with this week against last week.
- Data older than 90 days is pruned after each full run (`WARTRACK_KEEP_DAYS`); bounty snapshots older than a week keep one per day.
- `python3 scripts/smoke_pages.py` opens every page in headless Chrome and fails on a JavaScript error or a page that doesn't load its data (also run by the *Tests* workflow).
- **Player efficiency** (`efficiency.html`): for each Emerald Accord nation, the top 20 players with 1M+ damage over the last 7 days, ranked by wealth gained (or wealth) per 1M damage, with each player's build. Build = share of skill points in companies, energy, management and production (a level-L skill costs 1+2+…+L points): War ≤ 20%, Eco > 50%, Hybrid in between. The collector snapshots wealth and total damage once a day (`player_snap`) for the players with the most weekly damage in each nation, and refreshes skills daily or after a reset.
- **Backups:** the *Weekly backup* workflow (Sundays) copies the history database to `backup/state-YYYY-MM-DD`, keeping the newest 4. `state.sh restore` falls back to the newest backup if the `state` branch is missing or damaged, and `state.sh save` refuses to store a damaged or emptied database.
- **EA Money Transfers** has two tabs: transfers between nations, and citizen donations (totals, nation/citizen/amount filters, sortable tables, donations per day).
- Closed mercenary contracts are re-read every 3 hours (`WARTRACK_CONTRACTS_FULL_H`), active ones every run.
