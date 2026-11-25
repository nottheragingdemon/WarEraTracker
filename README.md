# WarEra Tracker

Dashboard for WarEra battle damage, orders, bounty, contracts and citizens' company locations/taxes,
filterable by alliance, country, MU and player. Data comes from `api2.warera.io`.

- `streamlit_app.py` serves `site/index.html` with `site/data.json` inlined (deploy on Streamlit Community Cloud).
- `.github/workflows/refresh.yml` runs hourly: restores the history database from the `state` branch, collects new data,
  rebuilds `site/data.json`, saves the database back to `state` (one force-pushed commit) and commits `data.json`.
- `wartrack/` is the collector/exporter (standard library only). `scope.json` limits collection to The Emerald Accord's battles since 2026-11-10.

## Set up
1. Repo **Settings → Secrets and variables → Actions → New repository secret**: `WARERA_API_KEY` = your API key.
2. Repo **Settings → Actions → General → Workflow permissions: Read and write**.
3. **Actions → Refresh data → Run workflow** once.
4. On https://share.streamlit.io choose **Create app**, pick this repo, branch `main`, file `streamlit_app.py`.

The API key is never stored in the repo. This repo is public, so the `state` branch (the collected game data) is public too.

Run locally: `WARERA_API_KEY=... sh refresh.sh` then `uv run streamlit run streamlit_app.py`.

## Apps
`site/index.html` (WarEra Tracker), `site/company.html` (Company tax tracker) and `site/ask.html` (Ask Claude: plain-English questions answered as tables; needs Claude's artifact runtime). `streamlit_app.py` serves the first two with navigation.

## Alerts (optional)
Add a repository secret `ALERT_WEBHOOK_URL` (a Discord or Slack incoming webhook). Each hourly refresh then posts: new battles involving the tracked alliance's countries; new contracts for those battles (grouped per battle); and bounty postings (a new entry or a rise of at least `ALERT_BOUNTY_MIN`, default 10,000) on players, MUs and countries of the alliance, with the active battle noted when there is one. The API doesn't tie bounties to a battle, so they are linked through the country. The first run only records a baseline.

## Tax sampling
`.github/workflows/tax-sample.yml` records region tax rates every 15 minutes (one public API call), so tax history is finer than the hourly refresh. The page shows a warning when `data.json` is more than 3 hours old.
